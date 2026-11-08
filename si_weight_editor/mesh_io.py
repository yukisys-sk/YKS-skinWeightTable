"""メッシュの頂点ウェイト読み書き（Edit / Object / Weight Paint モード共通）。

Edit モードでは bmesh の deform レイヤーを、それ以外では ``mesh.vertices`` を使う。
Edit モードで ``mesh.vertices[i].groups`` へ書いてもモード切替で失われるため、
読み書きは必ずこのモジュールを経由する。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import bmesh
import bpy

Weights = dict[int, dict[str, float]]


def armature_of(obj: bpy.types.Object) -> bpy.types.Object | None:
    """メッシュに付いている Armature モディファイアの対象を返す。

    Args:
        obj: メッシュオブジェクト。

    Returns:
        アーマチュアオブジェクト。無ければ None。
    """
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object is not None:
            return mod.object
    return None


def influence_names(obj: bpy.types.Object, deform_only: bool = True) -> list[str]:
    """スキンのインフルエンスとして扱う頂点グループ名の一覧を返す。

    Args:
        obj: メッシュオブジェクト。
        deform_only: True ならアーマチュアの deform ボーンと同名のグループだけ。
            アーマチュアが無い場合は全グループ。

    Returns:
        頂点グループ名（インデックス順）。
    """
    names = [vg.name for vg in obj.vertex_groups]
    arm = armature_of(obj)
    if deform_only and arm is not None:
        bones = {b.name for b in arm.data.bones if b.use_deform}
        names = [n for n in names if n in bones]
    return names


@contextmanager
def _edit_bmesh(obj: bpy.types.Object, create: bool = False) -> Iterator[tuple[bmesh.types.BMesh, object]]:
    """Edit モード中の bmesh と deform レイヤーを取り出すコンテキスト。

    Args:
        obj: Edit モード中のメッシュオブジェクト。
        create: True なら deform レイヤーが無いとき作成する（読み取りでは作らない）。

    Yields:
        ``(bmesh, deform レイヤー）``。レイヤーが無く作成もしない場合は None。
    """
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    layer = bm.verts.layers.deform.verify() if create else bm.verts.layers.deform.active
    yield bm, layer


def selected_vertices(obj: bpy.types.Object) -> list[int]:
    """選択中の頂点番号を返す。

    Args:
        obj: メッシュオブジェクト。

    Returns:
        昇順の頂点番号。
    """
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        return [v.index for v in bm.verts if v.select]
    return [v.index for v in obj.data.vertices if v.select]


def vertex_count(obj: bpy.types.Object) -> int:
    """頂点数を返す（Edit モードでも最新値）。

    Args:
        obj: メッシュオブジェクト。

    Returns:
        頂点数。
    """
    if obj.mode == "EDIT":
        return len(bmesh.from_edit_mesh(obj.data).verts)
    return len(obj.data.vertices)


def read_weights(obj: bpy.types.Object, verts: list[int]) -> Weights:
    """指定頂点のウェイトを ``{頂点: {グループ名: 値}}`` で読む。

    Args:
        obj: メッシュオブジェクト。
        verts: 頂点番号。

    Returns:
        頂点ごとのウェイト。所属グループの無い頂点は空の辞書。
    """
    index_name = {vg.index: vg.name for vg in obj.vertex_groups}
    out: Weights = {}
    if obj.mode == "EDIT":
        with _edit_bmesh(obj) as (bm, layer):
            for i in verts:
                items = bm.verts[i][layer].items() if layer is not None else ()
                out[i] = {index_name[g]: w for g, w in items if g in index_name}
    else:
        mverts = obj.data.vertices
        for i in verts:
            out[i] = {index_name[g.group]: g.weight for g in mverts[i].groups if g.group in index_name}
    return out


def write_weights(obj: bpy.types.Object, weights: Weights, create_groups: bool = False) -> None:
    """頂点ウェイトを書き込む。値が 0 以下のグループ所属は外す。

    Args:
        obj: メッシュオブジェクト。
        weights: ``{頂点: {グループ名: 値}}``。ここに無いグループは触らない。
        create_groups: True なら存在しないグループを作成する。

    Raises:
        KeyError: ``create_groups`` が False で、存在しないグループ名が含まれる場合。
    """
    names = {n for w in weights.values() for n in w}
    for name in names:
        if name not in obj.vertex_groups:
            if not create_groups:
                raise KeyError(f"頂点グループ {name!r} が {obj.name!r} にありません")
            obj.vertex_groups.new(name=name)
    name_index = {vg.name: vg.index for vg in obj.vertex_groups}
    if obj.mode == "EDIT":
        with _edit_bmesh(obj, create=True) as (bm, layer):
            for i, row in weights.items():
                dv = bm.verts[i][layer]
                for name, w in row.items():
                    gi = name_index[name]
                    if w > 0.0:
                        dv[gi] = w
                    elif gi in dv:
                        del dv[gi]
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return
    for i, row in weights.items():
        assigned = {g.group for g in obj.data.vertices[i].groups}
        for name, w in row.items():
            vg = obj.vertex_groups[name]
            if w > 0.0:
                vg.add([i], w, "REPLACE")
            elif vg.index in assigned:
                vg.remove([i])
    obj.data.update()


def neighbors(obj: bpy.types.Object) -> list[list[int]]:
    """全頂点の隣接頂点（エッジで繋がる頂点）を返す。

    Args:
        obj: メッシュオブジェクト。

    Returns:
        頂点番号をインデックスとする隣接頂点リスト。
    """
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        return [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    adj: list[list[int]] = [[] for _ in obj.data.vertices]
    for e in obj.data.edges:
        a, b = e.vertices
        adj[a].append(b)
        adj[b].append(a)
    return adj


def vertex_positions(obj: bpy.types.Object, world: bool = True) -> list[tuple[float, float, float]]:
    """全頂点の座標を返す。

    Args:
        obj: メッシュオブジェクト。
        world: True ならワールド座標、False ならローカル座標。

    Returns:
        頂点番号順の座標。
    """
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        co = [v.co.copy() for v in bm.verts]
    else:
        co = [v.co.copy() for v in obj.data.vertices]
    if world:
        co = [obj.matrix_world @ c for c in co]
    return [(c.x, c.y, c.z) for c in co]


def set_selected_vertices(obj: bpy.types.Object, verts: set[int]) -> None:
    """選択頂点を ``verts`` だけにする。

    Args:
        obj: メッシュオブジェクト。
        verts: 選択する頂点番号。
    """
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            v.select_set(v.index in verts)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return
    for v in obj.data.vertices:
        v.select = v.index in verts
    obj.data.update()


def ensure_armature(obj: bpy.types.Object, arm: bpy.types.Object | None) -> None:
    """``obj`` に Armature モディファイアが無ければ ``arm`` で追加する（自動バインド）。

    Args:
        obj: メッシュオブジェクト。
        arm: バインド先のアーマチュア。None なら何もしない。
    """
    if arm is None or armature_of(obj) is not None:
        return
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
