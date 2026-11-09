"""ウェイトテーブルの構築・更新とセル単位の編集ヘルパー。

テーブルの実体は ``WindowManager.siwe`` のコレクション（rows / cols / cells）。
セルは ``cells[行 * 列数 + 列]`` に行優先で並ぶ。
"""

from __future__ import annotations

import json
from typing import Callable

import bpy

from . import mesh_io
from .core import weight_math as wm

MAX_TABLE_ROWS = 2000
generation = 0  # refresh / clear のたびに増える。Qt のモデルが再読み込みの要否を判断する
LOCK_KEY = "siwe_locks"
EPS = 1e-6


def settings(context: bpy.types.Context):
    """UI 設定を返す。

    Args:
        context: 現在のコンテキスト。

    Returns:
        ``SIWE_Settings``。
    """
    return context.window_manager.siwe


def active_mesh(context: bpy.types.Context) -> bpy.types.Object | None:
    """アクティブなメッシュオブジェクトを返す。

    Args:
        context: 現在のコンテキスト。

    Returns:
        メッシュオブジェクト。無ければ None。
    """
    obj = getattr(context, "object", None)  # ファイル読み込み直後のタイマーでは属性が無いことがある
    return obj if obj is not None and obj.type == "MESH" else None


def load_locks(obj: bpy.types.Object) -> dict[int, set[str]]:
    """オブジェクトのカスタムプロパティからセルロックを読む。

    Args:
        obj: メッシュオブジェクト。

    Returns:
        ``{頂点番号: ロック中のインフルエンス名の集合}``。
    """
    raw = obj.get(LOCK_KEY)
    if not raw:
        return {}
    try:
        return {int(k): set(v) for k, v in json.loads(raw).items()}
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{obj.name!r} の {LOCK_KEY} が壊れています。Clear Locks で消去してください: {exc}") from exc


def save_locks(obj: bpy.types.Object, locks: dict[int, set[str]]) -> None:
    """セルロックをオブジェクトのカスタムプロパティへ保存する。

    Args:
        obj: メッシュオブジェクト。
        locks: ``{頂点番号: ロック中のインフルエンス名の集合}``。
    """
    data = {str(k): sorted(v) for k, v in locks.items() if v}
    if data:
        obj[LOCK_KEY] = json.dumps(data)
    elif LOCK_KEY in obj:
        del obj[LOCK_KEY]


def clear(s) -> None:
    """テーブルを空にする。

    Args:
        s: UI 設定。
    """
    global generation
    generation += 1
    s.rows.clear()
    s.cols.clear()
    s.cells.clear()
    s.object_name = ""


def refresh(context: bpy.types.Context, keep_selection: bool = True) -> None:
    """現在の選択からテーブルを作り直す。

    Args:
        context: 現在のコンテキスト。
        keep_selection: True なら同じ (頂点, インフルエンス) のセル選択を引き継ぐ。
    """
    global generation
    generation += 1
    s = settings(context)
    obj = active_mesh(context)
    if obj is None:
        clear(s)
        return
    old = {}
    if keep_selection and s.object_name == obj.name and len(s.cells):
        # セルへのランダムアクセスは極端に遅い（Edit モードで数万セルだと十数秒）ため一括取得する
        nc = len(s.cols)
        flags = [False] * len(s.cells)
        s.cells.foreach_get("selected", flags)
        row_verts = [0] * len(s.rows)
        s.rows.foreach_get("vert", row_verts)
        col_names = [c.name for c in s.cols]
        for i, on in enumerate(flags):
            if on:
                old[(row_verts[i // nc], col_names[i % nc])] = True
    old_col_sel = {c.name for c in s.cols if c.selected} if keep_selection else set()

    verts = mesh_io.selected_vertices(obj)[:MAX_TABLE_ROWS]
    names = mesh_io.influence_names(obj, not s.show_all_influences)
    weights = mesh_io.read_weights(obj, verts)
    locks = load_locks(obj)

    s.rows.clear()
    s.cols.clear()
    s.cells.clear()
    if s.object_name != obj.name:
        s.object_name = obj.name
    totals = {n: 0.0 for n in names}
    row_total: list[float] = []
    row_count: list[int] = []
    for v in verts:
        w = weights[v]
        row_total.append(sum(w.get(n, 0.0) for n in names))
        row_count.append(sum(1 for n in names if w.get(n, 0.0) > EPS))
        for n in names:
            totals[n] += w.get(n, 0.0)
    rows = s.rows
    add_row = rows.add
    for _ in verts:
        add_row()
    if verts:
        rows.foreach_set("vert", verts)
        rows.foreach_set("total", row_total)
        rows.foreach_set("count", row_count)
    terms = [t.lower() for t in s.search.split()]
    col_visible: list[bool] = []
    for n in names:
        nonzero = totals[n] > EPS or not s.filter_zero
        if terms:
            hit = all(t in n.lower() for t in terms)
            col_visible.append((nonzero and hit) if s.search_mode == "REFINE" else (nonzero or hit))
        else:
            col_visible.append(nonzero)
    for n in names:
        s.cols.add()
    if names:
        for col, n in zip(s.cols, names):
            col.name = n
        s.cols.foreach_set("selected", [n in old_col_sel for n in names])
        s.cols.foreach_set("visible", col_visible)
    # プロパティを 1 つずつ代入すると Edit モードで極端に遅い（数万セルで十数秒）ため、一括で設定する
    values: list[float] = []
    locked: list[bool] = []
    selected: list[bool] = []
    for v in verts:
        w = weights[v]
        lock_v = locks.get(v, ())
        for n in names:
            values.append(w.get(n, 0.0))
            locked.append(n in lock_v)
            selected.append(old.get((v, n), False))
    cells = s.cells
    add_cell = cells.add
    for _ in values:
        add_cell()
    if values:
        cells.foreach_set("value", values)
        cells.foreach_set("locked", locked)
        cells.foreach_set("selected", selected)
    limit = max(len(verts) - 1, 0)
    if s.row_offset > limit:
        s.row_offset = limit


def cell_flags(s, attr: str) -> list:
    """全セルの ``attr`` を一括取得する（セルへのランダムアクセスは遅いため）。

    Args:
        s: UI 設定。
        attr: ``selected`` / ``locked`` / ``value``。

    Returns:
        セル順の値のリスト。
    """
    data = [0.0 if attr == "value" else False] * len(s.cells)
    s.cells.foreach_get(attr, data)
    return data


def selected_cells(s) -> list[tuple[int, int]]:
    """選択中のセルを ``(行, 列)`` の昇順で返す。

    Args:
        s: UI 設定。

    Returns:
        ``(行番号, 列番号)`` のリスト。
    """
    nc = len(s.cols)
    return [(i // nc, i % nc) for i, on in enumerate(cell_flags(s, "selected")) if on] if nc else []


def edit_rows(
    context: bpy.types.Context,
    fn: Callable[[int, list[float], set[int], list[int]], list[float] | None],
    only_selected_rows: bool = True,
) -> int:
    """行ごとに ``fn`` で新しいウェイトを計算して書き戻し、テーブルを更新する。

    Args:
        context: 現在のコンテキスト。
        fn: ``fn(行番号, 現在のウェイト行, ロック列, 選択列) -> 新しいウェイト行`` 。
            None を返した行は書き込まない。
        only_selected_rows: True ならセルが 1 つ以上選択された行だけ処理する。

    Returns:
        書き込んだ頂点数。

    Raises:
        RuntimeError: アクティブなメッシュが無い、またはテーブルが空の場合。
    """
    s = settings(context)
    obj = active_mesh(context)
    if obj is None or not len(s.rows):
        raise RuntimeError("編集対象がありません。メッシュを選択し、頂点を選んでください")
    nc = len(s.cols)
    by_row: dict[int, list[int]] = {}
    for r, c in selected_cells(s):
        by_row.setdefault(r, []).append(c)
    targets = by_row if only_selected_rows else {r: by_row.get(r, []) for r in range(len(s.rows))}
    # キャッシュではなく現在のメッシュから読む（Undo やネイティブ操作後の古い値で上書きしないため）
    names = [c.name for c in s.cols]
    lock_flags = cell_flags(s, "locked")
    current = mesh_io.read_weights(obj, [s.rows[r].vert for r in targets])
    out = {}
    for r, cols in targets.items():
        live = current[s.rows[r].vert]
        locked = {c for c in range(nc) if lock_flags[r * nc + c]}
        new = fn(r, [live.get(n, 0.0) for n in names], locked, cols)
        if new is None:
            continue
        out[s.rows[r].vert] = {s.cols[c].name: new[c] for c in range(nc)}
    if out:
        mesh_io.write_weights(obj, out)
    refresh(context, keep_selection=True)
    return len(out)


def to_scale(s, raw: float) -> float:
    """内部値（0〜1）を表示スケールの値へ変換する。

    Args:
        s: UI 設定。
        raw: 内部値。

    Returns:
        表示用の値。
    """
    return raw * float(s.display_scale)


def from_scale(s, shown: float) -> float:
    """表示スケールの値を内部値（0〜1）へ変換する。

    Args:
        s: UI 設定。
        shown: 表示スケールの値。

    Returns:
        内部値。
    """
    return shown / float(s.display_scale)


def apply_input(context: bpy.types.Context) -> int:
    """入力欄の値を選択セルへ適用する（モード・正規化・ロックを考慮）。

    Args:
        context: 現在のコンテキスト。

    Returns:
        書き込んだ頂点数。
    """
    s = settings(context)
    value = from_scale(s, s.value)

    def fn(r, row, locked, cols):
        """1 行分の入力適用と正規化。"""
        edited = wm.apply_input(row, cols, locked, s.input_mode, value, s.unlimited)
        out, bake = wm.normalize_row(edited, row, cols, locked, force=s.normalize, unlimited=s.unlimited)
        return out if bake else None

    return edit_rows(context, fn)
