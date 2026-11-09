"""Qt のアプリケーションとイベント処理を Blender のタイマーに載せる。"""

from __future__ import annotations

import bpy

PUMP_INTERVAL = 0.02
_windows: list = []
_app = None


def _pump() -> float | None:
    """Qt のイベントを処理するタイマー関数。ウィンドウが無くなったら止める。

    Returns:
        次回実行までの秒数。None なら停止。
    """
    _windows[:] = [w for w in _windows if w.isVisible()]
    if _app is not None:
        _app.processEvents()
    return PUMP_INTERVAL if _windows else None


def ensure_app():
    """``QApplication`` を 1 つだけ作って返す（ウィジェットを作る前に必ず呼ぶ）。

    Returns:
        共有の ``QApplication``。
    """
    global _app
    from PySide6 import QtWidgets

    if _app is None:
        _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        _app.setQuitOnLastWindowClosed(False)
    return _app


def show(window) -> None:
    """ウィンドウを表示し、イベント処理のタイマーを開始する。

    Args:
        window: 表示する ``QWidget``。``ensure_app`` の後に作ったものであること。
    """
    ensure_app()
    window.show()
    _windows.append(window)
    if not bpy.app.timers.is_registered(_pump):
        bpy.app.timers.register(_pump, first_interval=PUMP_INTERVAL)


def close_all() -> None:
    """開いている Qt ウィンドウをすべて閉じ、タイマーを止める。"""
    for w in list(_windows):
        w.close()
    _windows.clear()
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
