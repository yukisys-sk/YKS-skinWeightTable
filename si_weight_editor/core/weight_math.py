"""ウェイト計算の純粋関数群（bpy 非依存）。

1 頂点のウェイトは「インフルエンス列ごとの値のリスト」で表す。
元の SIWeightEditor（Maya 版）の入力・正規化・制限・丸めの仕様を移植している。
すべての関数は引数を変更せず、新しいリストを返す。
"""

from __future__ import annotations

from typing import Iterable, Sequence

ABS = "ABS"
ADD = "ADD"
ADD_PERCENT = "ADD_PERCENT"

_EPS = 1e-10


def apply_input(
    weights: Sequence[float],
    columns: Iterable[int],
    locked: Iterable[int],
    mode: str,
    value: float,
    unlimited: bool = False,
) -> list[float]:
    """選択カラムに入力値を適用した新しいウェイト行を返す。

    Args:
        weights: 現在のウェイト行（0.0〜1.0）。
        columns: 入力対象のカラム番号。
        locked: ロックされているカラム番号。ロック列は変更しない。
        mode: ``ABS``（絶対値）/ ``ADD``（加算）/ ``ADD_PERCENT``（率加算）。
        value: 入力値（0.0〜1.0 スケール。ADD では差分、ADD_PERCENT では比率）。
        unlimited: True なら 1.0 を超える値を許容する。

    Returns:
        入力適用後のウェイト行（正規化前）。

    Raises:
        ValueError: ``mode`` が未知の場合。
    """
    if mode not in (ABS, ADD, ADD_PERCENT):
        raise ValueError(f"未知の入力モードです: {mode!r}（ABS / ADD / ADD_PERCENT のいずれか）")
    locked_set = set(locked)
    result = list(weights)
    for col in columns:
        if col in locked_set:
            continue
        if mode == ABS:
            new = max(0.0, min(value, 1.0))
        else:
            org = result[col]
            new = org + value if mode == ADD else org * (1.0 + value)
            if not unlimited:
                new = min(new, 1.0)
            new = max(new, 0.0)
        result[col] = new
    return result


def normalize_row(
    weights: Sequence[float],
    original: Sequence[float],
    columns: Iterable[int],
    locked: Iterable[int],
    force: bool = False,
    unlimited: bool = False,
    enforce: int = 0,
) -> tuple[list[float], bool]:
    """入力で編集したカラムを優先して、行の合計を 1.0 に正規化する。

    編集カラム（``columns``）以外は比率を保ったまま残りを分配し、ロック列は固定する。

    Args:
        weights: 編集後（正規化前）のウェイト行。
        original: 編集前のウェイト行。分配先が無いときの復帰に使う。
        columns: 今回編集したカラム番号。
        locked: ロックされているカラム番号。
        force: True なら合計が 1.0 以下でも正規化する（Normalize 有効時）。
        unlimited: True なら合計が 1.0 を超えても強制正規化しない。
        enforce: 0 以外のとき、強制正規化扱いにする（インフルエンス制限後など）。

    Returns:
        ``(新しいウェイト行, 書き込む必要があるか)`` のタプル。
    """
    new = list(weights)
    total = sum(new)
    do_norm = force or enforce != 0 or (total > 1.0 + _EPS and not unlimited)
    if not do_norm:
        return new, True

    locked_set = set(locked)
    cols = set(columns) - locked_set
    locked_sum = sum(new[i] for i in locked_set if i < len(new))
    if locked_sum >= 1.0:
        return [w if i in locked_set else 0.0 for i, w in enumerate(new)], True

    select_sum = sum(new[i] for i in cols)
    other_sum = sum(w for i, w in enumerate(new) if i not in cols and i not in locked_set)
    if other_sum + select_sum == 0.0:
        new = list(original)
        select_sum = sum(new[i] for i in cols)
        other_sum = sum(w for i, w in enumerate(new) if i not in cols and i not in locked_set)

    if select_sum + locked_sum >= 1.0:
        out = []
        for i, w in enumerate(new):
            if i in locked_set:
                out.append(w)
            elif i in cols:
                out.append(w / select_sum * (1.0 - locked_sum))
            else:
                out.append(0.0)
        return out, True

    all_sum = select_sum + locked_sum
    bake = True
    if other_sum == 0.0:
        if select_sum == 0.0 and not enforce:
            bake = False
        ratio = (1.0 - locked_sum) / select_sum if select_sum != 0.0 else 0.0
        other_ratio = 0.0
    else:
        ratio = 1.0
        other_ratio = (1.0 - all_sum) / other_sum
    out = []
    for i, w in enumerate(new):
        if i in locked_set:
            out.append(w)
        elif i in cols:
            out.append(w * ratio)
        else:
            out.append(w * other_ratio)
    return out, bake


def enforce_influence_limit(
    weights: Sequence[float], limit: int, locked: Iterable[int] = ()
) -> list[float]:
    """使用インフルエンス数を ``limit`` 以下に減らす（大きい順に残す）。

    ロック列は数に含めて値を保持する。呼び出し側で :func:`normalize_row` を
    ``enforce`` 付きで通して合計を 1.0 に戻すこと。

    Args:
        weights: ウェイト行。
        limit: 残すインフルエンス数の上限（1 以上）。
        locked: ロックされているカラム番号。

    Returns:
        上限を超えた分を 0.0 にしたウェイト行。

    Raises:
        ValueError: ``limit`` が 1 未満の場合。
    """
    if limit < 1:
        raise ValueError(f"インフルエンス数の上限は 1 以上にしてください: {limit}")
    locked_set = {i for i in locked if i < len(weights)}
    lock_count = sum(1 for i in locked_set if weights[i] != 0.0)
    keep = max(limit - lock_count, 0)
    free = [(i, w) for i, w in enumerate(weights) if i not in locked_set and w != 0.0]
    if len(free) <= keep:
        return list(weights)
    free.sort(key=lambda iw: iw[1], reverse=True)
    drop = {i for i, _ in free[keep:]}
    return [0.0 if i in drop else w for i, w in enumerate(weights)]


def limit_row(weights: Sequence[float], limit: int) -> list[float]:
    """使用インフルエンス数を ``limit`` 以下にし、合計を元の合計に戻す（スムース後の Obey Max Influences 用）。

    Args:
        weights: ウェイト行。
        limit: 残すインフルエンス数の上限（1 以上）。

    Returns:
        上限を超えた分を 0.0 にし、残りを比例配分して元の合計に揃えた行。上限以下ならそのままのコピー。

    Raises:
        ValueError: ``limit`` が 1 未満の場合。
    """
    limited = enforce_influence_limit(weights, limit)
    total, kept = sum(weights), sum(limited)
    if kept <= 0.0 or total == kept:
        return limited
    scale = total / kept
    return [w * scale for w in limited]


def round_weights(weights: Sequence[float], digits: int) -> list[float]:
    """小数点以下 ``digits`` 桁に丸め、丸め誤差で合計がずれた分を最初の十分大きい値で補正する。

    Args:
        weights: ウェイト行。
        digits: 残す小数点以下の桁数（0 以上）。

    Returns:
        丸め後のウェイト行。

    Raises:
        ValueError: ``digits`` が負の場合。
    """
    if digits < 0:
        raise ValueError(f"桁数は 0 以上にしてください: {digits}")
    before = round(sum(weights), 10)
    rounded = [round(w, digits) for w in weights]
    diff = round(before - sum(rounded), 10)
    if diff != 0.0:
        for i, w in enumerate(rounded):
            if w > abs(diff):
                rounded[i] = round(w + diff, digits)
                break
    return rounded


def move_weights(
    weights: Sequence[float],
    sources: Iterable[int],
    targets: Iterable[int],
    locked: Iterable[int] = (),
) -> list[float]:
    """ソース列のウェイトを合算してゼロにし、ターゲット列へ均等に分配する。

    Args:
        weights: ウェイト行。
        sources: 移動元のカラム番号。
        targets: 移動先のカラム番号。
        locked: ロックされているカラム番号（移動元にも移動先にもならない）。

    Returns:
        移動後のウェイト行。移動先が無い場合は元のまま返す。
    """
    locked_set = set(locked)
    src = set(sources) - locked_set
    dst = set(targets) - locked_set - src
    out = list(weights)
    if not dst:
        return out
    total = 0.0
    for i in src:
        total += out[i]
        out[i] = 0.0
    share = total / len(dst)
    for i in dst:
        out[i] += share
    return out


def smooth_rows(
    rows: Sequence[Sequence[float]],
    neighbors: Sequence[Sequence[int]],
    amount: float = 1.0,
    keep_zero: bool = False,
    iterations: int = 1,
    targets: Iterable[int] | None = None,
    include_self: bool = True,
) -> list[list[float]]:
    """隣接頂点との平均でウェイトをスムースする（ウェイトスムース/ハンマー用）。

    Args:
        rows: 頂点ごとのウェイト行。全行は同じ列数。
        neighbors: ``rows`` と同じ並びの隣接頂点インデックス（``rows`` 内の番号）。
        amount: 元の値とスムース後の値の混ぜ率（0.0〜1.0。1.0 で完全にスムース）。
        keep_zero: True なら元の値が 0.0 のカラムは 0.0 のまま保つ。
        iterations: 繰り返し回数。
        targets: 更新する行番号。None なら全行。対象外の行は参照のみで変更しない。
        include_self: False なら自分自身を平均に含めない（ウェイトハンマー相当）。

    Returns:
        スムース後のウェイト行（各行の合計は元の合計を保つ）。
    """
    amount = max(0.0, min(amount, 1.0))
    current = [list(r) for r in rows]
    originals = [list(r) for r in rows]
    target_set = set(range(len(rows))) if targets is None else set(targets)
    for _ in range(max(iterations, 1)):
        nxt = []
        for v, row in enumerate(current):
            nb = neighbors[v]
            if v not in target_set or not nb:
                nxt.append(list(row))
                continue
            group = ([row] if include_self else []) + [current[n] for n in nb]
            avg = [sum(g[c] for g in group) / len(group) for c in range(len(row))]
            if keep_zero:
                avg = [a if originals[v][c] != 0.0 else 0.0 for c, a in enumerate(avg)]
            mixed = [o * (1.0 - amount) + a * amount for o, a in zip(row, avg)]
            total_before = sum(row)
            total_after = sum(mixed)
            if total_after > 0.0 and total_before > 0.0:
                mixed = [w * total_before / total_after for w in mixed]
            nxt.append(mixed)
        current = nxt
    return current


def tile_values(source: Sequence[float], count: int) -> list[float]:
    """コピー元の値を、ペースト先の数だけ先頭から繰り返して並べる。

    Args:
        source: コピー元の値のリスト（空不可）。
        count: ペースト先のセル数。

    Returns:
        長さ ``count`` のリスト。

    Raises:
        ValueError: ``source`` が空の場合。
    """
    if not source:
        raise ValueError("コピー元が空です。先にセルまたは頂点をコピーしてください")
    return [source[i % len(source)] for i in range(count)]
