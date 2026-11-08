"""Skin Weight Table for Blender（Maya 版 SIWeightEditor を元にした派生ツール）。"""

import bpy
from bpy.app.handlers import persistent

from . import ops_table, ops_tools, props, table, ui

_signature: tuple | None = None
TIMER_INTERVAL = 0.3


def _auto_update() -> float:
    """選択が変わったらテーブルを更新するタイマー関数。

    Returns:
        次回実行までの秒数。
    """
    global _signature
    try:
        wm = bpy.context.window_manager
        s = wm.siwe
        obj = bpy.context.object
        if s.auto_update and not s.lock_ui and obj is not None and obj.type == "MESH":
            sig = (obj.name, obj.mode, hash(tuple(table.mesh_io.selected_vertices(obj))), len(obj.vertex_groups))
            if sig != _signature:
                _signature = sig
                table.refresh(bpy.context)
                for win in wm.windows:
                    for area in win.screen.areas:
                        if area.type in {"VIEW_3D", "PROPERTIES"}:
                            area.tag_redraw()
    except Exception as exc:  # タイマーは落とさず、原因をコンソールへ出す
        print(f"[Skin Weight Table] 自動更新に失敗しました: {exc!r}")
    return TIMER_INTERVAL


@persistent
def _invalidate(*_args) -> None:
    """Undo / Redo 後にテーブルを必ず作り直させる。"""
    global _signature
    _signature = None


def register() -> None:
    """プロパティ・オペレーター・パネルを登録し、自動更新タイマーを開始する。"""
    props.register()
    for cls in ops_table.CLASSES + ops_tools.CLASSES + ui.CLASSES:
        bpy.utils.register_class(cls)
    ui.register_menu()
    bpy.app.handlers.undo_post.append(_invalidate)
    bpy.app.handlers.redo_post.append(_invalidate)
    bpy.app.timers.register(_auto_update, persistent=True)


def unregister() -> None:
    """登録したものをすべて解除する。"""
    ui.unregister_menu()
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _invalidate in handlers:
            handlers.remove(_invalidate)
    if bpy.app.timers.is_registered(_auto_update):
        bpy.app.timers.unregister(_auto_update)
    for cls in reversed(ops_table.CLASSES + ops_tools.CLASSES + ui.CLASSES):
        bpy.utils.unregister_class(cls)
    props.unregister()
