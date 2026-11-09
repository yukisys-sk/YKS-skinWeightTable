"""Qt ウィンドウの GUI テスト（PySide6 が使える Blender で実行する）。

実行: blender --python tests/blender_qt_window.py
環境変数 SIWE_PYSIDE_PATH に PySide6 の入ったフォルダを指定すると sys.path に加える。
SIWE_SHOT_DIR を指定すると、ウィンドウのスクリーンショットをそこへ保存する。
"""

import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if os.environ.get("SIWE_PYSIDE_PATH"):
    sys.path.insert(0, os.environ["SIWE_PYSIDE_PATH"])
import si_weight_editor as siwe  # noqa: E402
from si_weight_editor import mesh_io, table  # noqa: E402
from si_weight_editor.qt import runtime  # noqa: E402

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """検証結果を記録して表示する。"""
    RESULTS.append(ok)
    print(f"QTTEST {'OK' if ok else 'NG'} {name} {detail}")


def setup() -> None:
    """メッシュと頂点グループを作り、頂点を選んで Qt ウィンドウを開く。"""
    siwe.register()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=2)
    obj = bpy.context.object
    for n in ("spine", "arm.L", "arm.R", "upperArm_twist_01"):
        obj.vertex_groups.new(name=n)
    obj.vertex_groups["spine"].add(list(range(25)), 0.6, "REPLACE")
    obj.vertex_groups["arm.L"].add(list(range(25)), 0.4, "REPLACE")
    mesh_io.set_selected_vertices(obj, set(range(8)))
    bpy.ops.ed.undo_push(message="setup")
    s = bpy.context.window_manager.siwe
    s.filter_zero = True
    result = bpy.ops.siwe.open_qt_window()
    check("open", result == {"FINISHED"} and len(runtime._windows) == 1)


def obj_():
    """メッシュを名前で引く（Undo 後は古い参照が無効になるため、毎回引き直す）。"""
    return bpy.data.objects["Grid"]


def win():
    """開いている Qt ウィンドウを返す。"""
    return runtime._windows[0]


def test_table() -> None:
    """表のサイズと、見出し・値が反映されているかを確認する。"""
    w = win()
    check("rows", w.model.rowCount() == 8, str(w.model.rowCount()))
    check("cols (zero filtered)", w.model.columnCount() == 2, str(w.model.columnCount()))
    idx = w.model.index(0, 0)
    check("cell text", w.model.data(idx) == "0.600", str(w.model.data(idx)))
    from PySide6.QtCore import Qt
    check("header text", w.model.headerData(0, Qt.Orientation.Horizontal) == "spine")


def test_apply() -> None:
    """セルを選択して Apply し、Blender のウェイトが変わることと Undo を確認する。"""
    from PySide6.QtCore import QItemSelectionModel as S
    w = win()
    sel = w.view.selectionModel()
    sel.select(w.model.index(0, 1), S.SelectionFlag.Select)  # arm.L の 1 行目
    w.value_box.setValue(0.9)
    w.apply()
    got = mesh_io.read_weights(obj_(), [0])[0]
    check("apply abs", abs(got["arm.L"] - 0.9) < 1e-4 and abs(got["spine"] - 0.1) < 1e-4, str(got))
    check("model updated", w.model.data(w.model.index(0, 1)) == "0.900", str(w.model.data(w.model.index(0, 1))))
    bpy.ops.ed.undo()
    got = mesh_io.read_weights(obj_(), [0])[0]
    check("undo", abs(got["arm.L"] - 0.4) < 1e-4, str(got))
    w.reload(force=True)


def test_lock() -> None:
    """ロックしたセルが Apply で変わらないことを確認する。"""
    from PySide6.QtCore import QItemSelectionModel as S
    w = win()
    sel = w.view.selectionModel()
    sel.clear()
    sel.select(w.model.index(0, 0), S.SelectionFlag.Select)  # spine をロック
    w.run("siwe.lock", sync=True, mode="LOCK")
    check("lock flag", any(w.model.snap.locked))
    sel.clear()
    sel.select(w.model.index(0, 1), S.SelectionFlag.Select)
    w.value_box.setValue(0.9)
    w.apply()
    got = mesh_io.read_weights(obj_(), [0])[0]
    check("locked kept", abs(got["spine"] - 0.6) < 1e-4, str(got))
    w.run("siwe.lock", mode="CLEAR")


def test_edit_mode_undo() -> None:
    """Edit モードで Qt から Apply し、同じ Edit モードのまま Undo で戻ることを確認する（edit-mesh の Undo は別系統）。"""
    from PySide6.QtCore import QItemSelectionModel as S
    bpy.ops.object.mode_set(mode="EDIT")
    w = win()
    w.reload(force=True)
    w.view.selectionModel().clear()
    w.view.selectionModel().select(w.model.index(1, 1), S.SelectionFlag.Select)
    w.value_box.setValue(0.8)
    w.apply()
    got = mesh_io.read_weights(obj_(), [1])[1]
    check("edit-mode apply", abs(got["arm.L"] - 0.8) < 1e-4, str(got))
    bpy.ops.ed.undo()
    got = mesh_io.read_weights(obj_(), [1])[1]
    check("edit-mode undo", abs(got["arm.L"] - 0.4) < 1e-4, str(got))
    bpy.ops.object.mode_set(mode="OBJECT")
    win().reload(force=True)


def test_new_file_closes_window() -> None:
    """ウィンドウを開いたまま File > New しても、閉じられてクラッシュしないことを確認する。"""
    bpy.ops.wm.read_homefile(app_template="")
    check("new file closed window", len(runtime._windows) == 0, str(len(runtime._windows)))


def test_unregister_closes_window() -> None:
    """ウィンドウを開いたまま拡張機能を無効化（unregister）しても、閉じられてクラッシュしないことを確認する。"""
    bpy.ops.mesh.primitive_grid_add()
    mesh_io.set_selected_vertices(bpy.context.view_layer.objects.active, {0})
    from si_weight_editor.qt.window import _override
    with bpy.context.temp_override(**_override()):  # File > New 直後のタイマーには object が無いため、3D ビューのコンテキストで呼ぶ
        check("reopen", bpy.ops.siwe.open_qt_window() == {"FINISHED"} and len(runtime._windows) == 1)
    siwe.unregister()
    check("unregister closed window", len(runtime._windows) == 0)
    siwe.register()


def shot() -> None:
    """ウィンドウのスクリーンショットを保存する。"""
    out = os.environ.get("SIWE_SHOT_DIR")
    if out:
        win().grab().save(os.path.join(out, "qt_window.png"))


def finish() -> None:
    """結果を集計して Blender を終了する。"""
    runtime.close_all()
    print("QTTEST SUMMARY", "PASS" if all(RESULTS) else "FAIL", f"{sum(RESULTS)}/{len(RESULTS)}")
    bpy.ops.wm.quit_blender()


def schedule(steps) -> None:
    """各ステップを 0.6 秒間隔のタイマーで順に実行する。"""
    def make(fn, i):
        def run():
            try:
                fn()
            except Exception as exc:  # テスト失敗として記録して続行
                import traceback
                traceback.print_exc()
                check(fn.__name__, False, repr(exc))
            return None
        bpy.app.timers.register(run, first_interval=1.0 + 0.6 * i, persistent=True)
    for i, fn in enumerate(steps):
        make(fn, i)


schedule([setup, test_table, test_apply, test_lock, test_edit_mode_undo, shot,
          test_new_file_closes_window, test_unregister_closes_window, finish])
