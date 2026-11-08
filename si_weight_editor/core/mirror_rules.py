"""左右対称の命名規則（bpy 非依存）。

ルール文字列は元の SIWeightEditor と同じく ``.`` を 1 文字のワイルドカードとして扱う。
``.`` そのものを指したいときは ``\\.`` と書く（例: Blender 標準の ``\\.L`` ⇄ ``\\.R``）。
"""

from __future__ import annotations

from typing import Callable, Sequence

# (左, 右) の組。先頭から順に最初に一致したものを使う
DEFAULT_RULES: tuple[tuple[str, str], ...] = (
    (r"\.L", r"\.R"),
    (r"_L", r"_R"),
    ("Left", "Right"),
    ("left", "right"),
    ("_l_", "_r_"),
    ("L_", "R_"),
)


def _tokenize(pattern: str) -> list[tuple[str, bool]]:
    """ルール文字列を ``(文字, ワイルドカードか)`` のリストに分解する。

    Args:
        pattern: ルール文字列。

    Returns:
        トークン列。
    """
    tokens: list[tuple[str, bool]] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            tokens.append((pattern[i + 1], False))
            i += 2
            continue
        tokens.append((ch, ch == "."))
        i += 1
    return tokens


def _find(name: str, tokens: Sequence[tuple[str, bool]]) -> int:
    """``name`` の中でトークン列に一致する最初の位置を返す（無ければ -1）。

    Args:
        name: 検索対象の名前。
        tokens: :func:`_tokenize` の結果。

    Returns:
        一致開始位置。
    """
    n = len(tokens)
    for start in range(len(name) - n + 1):
        if all(wild or name[start + k] == ch for k, (ch, wild) in enumerate(tokens)):
            return start
    return -1


def mirror_name(
    name: str,
    rules: Sequence[tuple[str, str]] = DEFAULT_RULES,
    exists: Callable[[str], bool] | None = None,
) -> str | None:
    """名前を左右反転した名前を返す。

    Args:
        name: 元の名前（ボーン名・頂点グループ名）。
        rules: ``(左, 右)`` ルールの並び。左右どちらの向きでも検索する。
        exists: 指定すると、この関数が True を返す名前だけを採用する
            （``spine_Lower`` → ``spine_Rower`` のような部分一致の誤変換を防ぐ）。

    Returns:
        反転後の名前。どのルールにも一致しなければ ``None``。
    """
    for left, right in rules:
        lt, rt = _tokenize(left), _tokenize(right)
        for src, dst in ((lt, rt), (rt, lt)):
            pos = _find(name, src)
            if pos < 0:
                continue
            repl = []
            for k, (ch, wild) in enumerate(dst):
                if not wild:
                    repl.append(ch)
                elif k < len(src):
                    repl.append(name[pos + k])
            result = name[:pos] + "".join(repl) + name[pos + len(src):]
            if exists is None or exists(result):
                return result
    return None


def parse_rules(text: str) -> list[tuple[str, str]]:
    """``左,右`` を 1 行ずつ書いた文字列からルール表を作る。

    Args:
        text: 改行区切りのルール。空行と ``#`` で始まる行は無視する。

    Returns:
        ``(左, 右)`` のリスト。

    Raises:
        ValueError: カンマで 2 つに分かれない行がある場合（行番号付き）。
    """
    rules: list[tuple[str, str]] = []
    for no, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"{no} 行目は『左,右』の形式で書いてください: {line!r}")
        rules.append((parts[0], parts[1]))
    return rules
