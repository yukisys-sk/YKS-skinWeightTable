"""Blender 上でのスモークテスト。

実行: blender --background --factory-startup --python tests/blender_smoke.py
失敗時は例外で終了コード 1 になる。
"""

import sys
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import si_weight_editor as siwe  # noqa: E402
from si_weight_editor import mesh_io, table  # noqa: E402


def approx(a, b, tol=1e-4):
    """浮動小数の近似比較。"""
    return abs(a - b) <= tol


def build_scene():
    """5x5 グリッドメッシュ + 3 ボーンのアーマチュアを作る。

    Returns:
        ``(mesh_obj, armature_obj)``。
    """
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=2)
    mesh = bpy.context.object
    mesh.name = "Body"
    bpy.ops.object.armature_add()
    arm = bpy.context.object
    arm.name = "Rig"
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    eb[0].name = "spine"
    for i, n in enumerate(("arm.L", "arm.R")):
        b = eb.new(n)
        b.head, b.tail = (i, 0, 0), (i, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    for n in ("spine", "arm.L", "arm.R"):
        mesh.vertex_groups.new(name=n)
    mod = mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mesh.vertex_groups["spine"].add(list(range(len(mesh.data.vertices))), 1.0, "REPLACE")
    return mesh, arm


def select_verts(mesh, ids):
    """指定頂点だけを選択する。"""
    bpy.context.view_layer.objects.active = mesh
    for o in bpy.context.scene.objects:
        o.select_set(o == mesh)
    mesh_io.set_selected_vertices(mesh, set(ids))


def run():
    """全機能を順に実行して結果を検証する。"""
    siwe.register()
    s = bpy.context.window_manager.siwe
    mesh, arm = build_scene()
    ids = [0, 1, 2, 3]
    select_verts(mesh, ids)
    s.filter_zero = False
    table.refresh(bpy.context)
    assert len(s.rows) == 4 and len(s.cols) == 3, (len(s.rows), len(s.cols))

    # --- ABS + normalize
    bpy.ops.siwe.select_cells(mode="COL", index=1)
    s.input_mode, s.value = "ABS", 0.5
    assert bpy.ops.siwe.apply_input() == {"FINISHED"}
    w = mesh_io.read_weights(mesh, ids)
    assert approx(w[0]["arm.L"], 0.5) and approx(w[0]["spine"], 0.5), w[0]

    # --- ネイティブ操作で値が変わった後でも、キャッシュではなく現在値から計算する
    mesh.vertex_groups["spine"].add([0], 0.5, "REPLACE")
    mesh.vertex_groups["arm.L"].add([0], 0.5, "REPLACE")
    s.input_mode, s.value = "ABS", 0.0
    bpy.ops.siwe.select_cells(mode="NONE")
    bpy.ops.siwe.select_cells(mode="COL", index=1)
    assert bpy.ops.siwe.apply_input() == {"FINISHED"}
    w = mesh_io.read_weights(mesh, [0])
    assert "arm.L" not in w[0] and approx(w[0]["spine"], 1.0), w[0]
    s.input_mode, s.value = "ABS", 0.5
    bpy.ops.siwe.apply_input()

    # --- Add% / Add
    s.input_mode, s.value = "ADD", 0.2
    bpy.ops.siwe.apply_input()
    w = mesh_io.read_weights(mesh, ids)
    assert approx(w[1]["arm.L"], 0.7) and approx(w[1]["spine"], 0.3), w[1]

    # --- lock then change: locked cell keeps value
    bpy.ops.siwe.select_cells(mode="NONE")
    bpy.ops.siwe.select_cells(mode="COL", index=0)
    bpy.ops.siwe.lock(mode="LOCK")
    assert all(c.locked for i, c in enumerate(s.cells) if i % 3 == 0)
    bpy.ops.siwe.select_cells(mode="NONE")
    bpy.ops.siwe.select_cells(mode="COL", index=2)
    s.input_mode, s.value = "ABS", 0.3
    bpy.ops.siwe.apply_input()
    w = mesh_io.read_weights(mesh, ids)
    assert approx(w[0]["spine"], 0.3) and approx(w[0]["arm.R"], 0.3) and approx(w[0]["arm.L"], 0.4), w[0]
    bpy.ops.siwe.lock(mode="CLEAR")
    assert not any(c.locked for c in s.cells)

    # --- round / limit / bad rows
    s.digits, s.limit = 1, 2
    bpy.ops.siwe.round_off()
    bpy.ops.siwe.enforce_limit()
    w = mesh_io.read_weights(mesh, ids)
    assert all(sum(1 for x in r.values() if x > 1e-6) <= 2 and approx(sum(r.values()), 1.0) for r in w.values()), w
    s.bad_filter = "UNDER"
    assert bpy.ops.siwe.select_bad_rows() == {"FINISHED"}

    # --- smooth / hammer
    select_verts(mesh, [6, 7, 8])
    table.refresh(bpy.context)
    assert bpy.ops.siwe.smooth(hammer=False) == {"FINISHED"}
    assert bpy.ops.siwe.smooth(hammer=True) == {"FINISHED"}

    # --- cell / vertex / move
    select_verts(mesh, ids)
    table.refresh(bpy.context, keep_selection=False)
    bpy.ops.siwe.select_cells(mode="ROW", index=0)
    bpy.ops.siwe.cell_copy()
    bpy.ops.siwe.select_cells(mode="ROW", index=3)
    assert bpy.ops.siwe.cell_paste() == {"FINISHED"}
    bpy.ops.siwe.vertex_copy()
    select_verts(mesh, [10, 11])
    assert bpy.ops.siwe.vertex_paste() == {"FINISHED"}
    table.refresh(bpy.context)
    s.filter_zero = False
    table.refresh(bpy.context)
    bpy.ops.siwe.select_cells(mode="COL", index=0)
    bpy.ops.siwe.move_influence(step="COPY")
    bpy.ops.siwe.select_cells(mode="NONE")
    bpy.ops.siwe.select_cells(mode="COL", index=1)
    assert bpy.ops.siwe.move_influence(step="PASTE") == {"FINISHED"}
    w = mesh_io.read_weights(mesh, [10])
    assert approx(w[10].get("spine", 0.0), 0.0), w

    # --- Edit mode round trip
    select_verts(mesh, ids)
    bpy.ops.object.mode_set(mode="EDIT")
    table.refresh(bpy.context, keep_selection=False)
    s.input_mode, s.value = "ABS", 1.0
    bpy.ops.siwe.select_cells(mode="NONE")
    bpy.ops.siwe.select_cells(mode="COL", index=0)
    assert bpy.ops.siwe.apply_input() == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")
    w = mesh_io.read_weights(mesh, ids)
    assert approx(w[0]["spine"], 1.0) and "arm.L" not in w[0], w[0]

    # --- symmetry
    for v in mesh.data.vertices:
        mesh.vertex_groups["arm.L"].add([v.index], 0.0, "REPLACE")
    left = [v.index for v in mesh.data.vertices if v.co.x < -0.1]
    right_of = {v.index: v.index for v in mesh.data.vertices}
    for i in left:
        mesh.vertex_groups["arm.L"].add([i], 0.8, "REPLACE")
        mesh.vertex_groups["spine"].add([i], 0.2, "REPLACE")
    select_verts(mesh, [])
    s.mirror_direction = "NEG_TO_POS"
    assert bpy.ops.siwe.symmetrize() == {"FINISHED"}
    pos = [v.index for v in mesh.data.vertices if v.co.x > 0.1]
    got = mesh_io.read_weights(mesh, [pos[0]])[pos[0]]
    assert approx(got.get("arm.R", 0.0), 0.8), got
    assert "arm.L" not in got or approx(got["arm.L"], 0.0), got

    # --- simple copy / paste (index + position)
    bpy.ops.siwe.simple_copy()
    for vg in mesh.vertex_groups:
        vg.remove(list(range(len(mesh.data.vertices))))
    assert bpy.ops.siwe.simple_paste(method="INDEX") == {"FINISHED"}
    again = mesh_io.read_weights(mesh, [pos[0]])[pos[0]]
    assert approx(again.get("arm.R", 0.0), 0.8), again
    assert bpy.ops.siwe.simple_paste(method="POSITION") == {"FINISHED"}

    # --- transfer
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=2)
    tgt = bpy.context.object
    tgt.name = "Target"
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.siwe.transfer_copy()
    bpy.ops.object.select_all(action="DESELECT")
    tgt.select_set(True)
    bpy.context.view_layer.objects.active = tgt
    mesh_io.set_selected_vertices(tgt, {pos[0]})
    assert bpy.ops.siwe.transfer_paste() == {"FINISHED"}
    tw = mesh_io.read_weights(tgt, [pos[0]])[pos[0]]
    assert approx(tw.get("arm.R", 0.0), 0.8), tw

    # --- skin state / influences / go
    select_verts(mesh, [0])
    assert bpy.ops.siwe.toggle_mute() == {"FINISHED"}
    assert not mesh.modifiers["Armature"].show_viewport
    bpy.ops.siwe.toggle_mute()
    assert bpy.ops.siwe.bind_pose() == {"FINISHED"}
    s.new_influence = "extra"
    assert bpy.ops.siwe.add_influence() == {"FINISHED"} and "extra" in mesh.vertex_groups
    table.refresh(bpy.context, keep_selection=False)
    assert bpy.ops.siwe.remove_unused() == {"FINISHED"}
    assert "extra" in mesh.vertex_groups  # ボーンに対応しないグループはインフルエンスではないので残る
    bpy.ops.object.select_all(action="DESELECT")
    tgt.select_set(True)
    assert bpy.ops.siwe.go_export() == {"FINISHED"}
    assert bpy.ops.siwe.go_import() == {"FINISHED"}

    # --- 未呼び出しだった UI 系オペレーター
    select_verts(mesh, [0, 1, 2])
    table.refresh(bpy.context, keep_selection=False)
    s.filter_zero = False
    table.refresh(bpy.context)
    bpy.ops.siwe.select_cells(mode="COL", index=0)
    assert bpy.ops.siwe.show_cells(all=False) == {"FINISHED"}
    assert bpy.ops.siwe.show_cells(all=True) == {"FINISHED"}
    bpy.ops.siwe.select_cells(mode="ROW", index=0)
    assert bpy.ops.siwe.select_from_cells() == {"FINISHED"}
    assert bpy.ops.siwe.select_bones() == {"FINISHED"}
    assert any(pb.select for pb in arm.pose.bones) if "select" in bpy.types.PoseBone.bl_rna.properties else any(b.select for b in arm.data.bones)
    assert bpy.ops.siwe.page(axis="ROW", step=1) == {"FINISHED"}
    assert bpy.ops.siwe.page(axis="COL", step=-1) == {"FINISHED"}
    s.row_offset = s.col_offset = 0
    select_verts(mesh, [0])
    table.refresh(bpy.context, keep_selection=False)
    bpy.ops.siwe.select_cells(mode="COL", index=0)
    assert bpy.ops.siwe.set_fixed(value=1.0) == {"FINISHED"}
    assert approx(mesh_io.read_weights(mesh, [0])[0]["spine"], 1.0)
    assert bpy.ops.siwe.remove_influence() == {"FINISHED"}
    assert "spine" not in mesh.vertex_groups
    mesh.vertex_groups.new(name="spine")
    mesh.vertex_groups["spine"].add(list(range(len(mesh.data.vertices))), 1.0, "REPLACE")
    assert bpy.ops.siwe.clear_table() == {"FINISHED"} and len(s.rows) == 0

    # --- Simple Paste: 名前が違うメッシュ + 自動バインド
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.siwe.simple_copy()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=2)
    other = bpy.context.object
    other.name = "Renamed"
    assert bpy.ops.siwe.simple_paste(method="INDEX") == {"FINISHED"}
    assert mesh_io.armature_of(other) is arm and "spine" in other.vertex_groups

    # --- Freeze_M は現在のポーズ形状を変えない / Freeze はスキニングを外す
    mesh.name = "Body"
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    arm.pose.bones["arm.L"].rotation_mode = "XYZ"
    arm.pose.bones["arm.L"].rotation_euler = (0.0, 0.8, 0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh.scale = (2.0, 2.0, 2.0)

    def evaluated(obj):
        """評価後（ポーズ適用後）のワールド頂点座標。"""
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        return [tuple(ev.matrix_world @ v.co) for v in ev.data.vertices]

    before = evaluated(mesh)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    assert bpy.ops.siwe.freeze(keep_skin=True) == {"FINISHED"}
    assert any(m.type == "ARMATURE" for m in mesh.modifiers)
    after = evaluated(mesh)
    assert all(all(approx(a, b) for a, b in zip(p, q)) for p, q in zip(before, after)), "Freeze_M で形状が変わった"
    assert bpy.ops.siwe.freeze(keep_skin=False) == {"FINISHED"}
    assert not any(m.type == "ARMATURE" for m in mesh.modifiers) and "arm.L" in mesh.vertex_groups

    # --- Auto Symmetry は L/R グループを入れ替える / Merge
    mesh_io.ensure_armature(mesh, arm)
    for v in mesh.data.vertices:
        mesh.vertex_groups["arm.L"].add([v.index], 0.0, "REPLACE")
        mesh.vertex_groups["arm.R"].add([v.index], 0.0, "REPLACE")
    mesh.vertex_groups["arm.L"].add([3], 0.8, "REPLACE")
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    before_names = {o.name for o in bpy.context.scene.objects}
    assert bpy.ops.siwe.auto_symmetry() == {"FINISHED"}
    dup = [o for o in bpy.context.scene.objects if o.name not in before_names][0]
    gl = mesh_io.read_weights(dup, [3])[3]
    assert approx(gl.get("arm.R", 0.0), 0.8) and approx(gl.get("arm.L", 0.0), 0.0), gl
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    dup.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    assert bpy.ops.siwe.merge_skinned() == {"FINISHED"}

    # --- 別ウィンドウはバックグラウンド（ウィンドウ無し）では実行不可
    assert not bpy.ops.siwe.open_window.poll()

    siwe.unregister()
    print("SMOKE OK")


try:
    run()
except Exception:
    traceback.print_exc()
    sys.exit(1)
