"""GUI 起動でパネル描画を検証する（描画エラーはコンソールに出る）。

実行: blender --factory-startup --python tests/blender_gui_draw.py
"""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import si_weight_editor as siwe  # noqa: E402
from si_weight_editor import mesh_io, table  # noqa: E402


DRAWN: set = set()


def quit_later() -> None:
    """描画完了を待ってから終了する。"""
    print("DRAWN PANELS:", sorted(DRAWN))
    bpy.ops.wm.quit_blender()


def _tracked(orig, name):
    """draw をラップして、呼ばれたパネル名を DRAWN に記録する。

    Args:
        orig: 元の draw 関数。
        name: パネルクラス名。

    Returns:
        ``(self, context)`` だけを取る draw 関数。
    """

    def draw(self, context):
        """描画された印を残して元の draw を呼ぶ。"""
        DRAWN.add(name)
        orig(self, context)

    return draw


def step() -> None:
    """メッシュ作成→選択→テーブル構築→再描画し、数秒後に終了する。"""
    siwe.ui.SIWE_PT_main.bl_category = "Item"  # 既定で開くタブに置いて必ず描画させる
    for cls in siwe.ui.CLASSES:
        cls.bl_options = set()
        cls.draw = _tracked(cls.draw, cls.__name__)
    siwe.register()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=2)
    obj = bpy.context.object
    for n in ("a", "b"):
        obj.vertex_groups.new(name=n)
    obj.vertex_groups["a"].add(list(range(25)), 0.5, "REPLACE")
    obj.vertex_groups["b"].add(list(range(25)), 0.5, "REPLACE")
    mesh_io.set_selected_vertices(obj, {0, 1, 2})
    table.refresh(bpy.context)
    for area in bpy.context.screen.areas:
        area.tag_redraw()
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.show_region_ui = True
    print("GUI DRAW rows/cols:", len(bpy.context.window_manager.siwe.rows), len(bpy.context.window_manager.siwe.cols))
    bpy.app.timers.register(quit_later, first_interval=2.0)


bpy.app.timers.register(step, first_interval=1.0)
