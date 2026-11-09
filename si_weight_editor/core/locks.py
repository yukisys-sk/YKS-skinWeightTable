"""セルロックの列単位の操作（bpy 非依存）。"""

from __future__ import annotations

from typing import Iterable, Mapping


def toggle_column(locks: Mapping[int, set[str]], name: str, vertices: Iterable[int]) -> tuple[dict[int, set[str]], bool]:
    """インフルエンス 1 列のロックを切り替える（Maya 版の見出しダブルクリックと同じ挙動）。

    その列に 1 つでもロックがあれば全頂点をアンロックし、無ければ全頂点をロックする。
    引数は変更しない。

    Args:
        locks: ``{頂点番号: ロック中のインフルエンス名の集合}``。
        name: 対象のインフルエンス名。
        vertices: ロック対象とする全頂点の番号。

    Returns:
        ``(新しいロック情報, ロックしたなら True / アンロックしたなら False)``。
    """
    result = {v: set(names) for v, names in locks.items()}
    if any(name in names for names in result.values()):
        for names in result.values():
            names.discard(name)
        return {v: names for v, names in result.items() if names}, False
    for v in vertices:
        result.setdefault(v, set()).add(name)
    return result, True
