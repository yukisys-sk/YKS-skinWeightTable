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


def test_header_double_click() -> None:
    """見出しのダブルクリックで、その列が全頂点ロック → 再度でアンロックされることを確認する。"""
    w = win()
    w.reload(force=True)
    w.header.sectionDoubleClicked.emit(1)
    nc = len(w.model.snap.col_names)
    locked = w.model.snap.locked
    check("header lock", all(locked[r * nc + 1] for r in range(len(w.model.snap.verts))) and not any(locked[r * nc] for r in range(len(w.model.snap.verts))))
    w.header.sectionDoubleClicked.emit(1)
    check("header unlock", not any(w.model.snap.locked))


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


def test_tools() -> None:
    """サブツールのボタンが、Qt から実行でき、結果が表に反映されることを確認する。"""
    from PySide6.QtCore import QItemSelectionModel as S
    w = win()
    w.reload(force=True)
    sel = w.view.selectionModel()
    sel.clear()
    for r in range(w.model.rowCount()):
        for c in range(w.model.columnCount()):
            sel.select(w.model.index(r, c), S.SelectionFlag.Select)
    check("smooth", w.run("siwe.smooth", sync=True))
    check("hammer keep zero", w.run("siwe.smooth", sync=True, hammer=True, keep_zero=True))
    # スムース設定ウィンドウ: 値が本体の設定とツールバーに反映される
    w.open_smooth_settings()
    sw = w._smooth_settings
    sw.iterations.setValue(3)
    sw.ratio.setValue(40)
    sw.obey_limit.setChecked(True)
    s = w.settings()
    check("smooth settings applied", s.smooth_iterations == 3 and abs(s.smooth_amount - 0.4) < 1e-6 and s.smooth_obey_limit)
    check("smooth toolbar synced", w.iter_box.value() == 3 and w.ratio_box.value() == 40)
    w.ratio_box.setValue(70)
    check("smooth window synced back", sw.ratio.value() == 70)
    check("smooth with settings", w.run("siwe.smooth", sync=True))
    s.smooth_obey_limit = False
    sw.close()
    check("cell copy", w.run("siwe.cell_copy", sync=True))
    sel.clear()
    sel.select(w.model.index(0, 0), S.SelectionFlag.Select)
    check("cell paste", w.run("siwe.cell_paste", sync=True))
    check("vertex copy", w.run("siwe.vertex_copy"))
    check("vertex paste", w.run("siwe.vertex_paste"))
    check("simple copy", w.run("siwe.simple_copy"))
    check("simple paste index", w.run("siwe.simple_paste", method="INDEX"))
    w.influence_edit.setText("extra")
    check("add influence", w.run("siwe.add_influence") and "extra" in obj_().vertex_groups)
    check("remove unused is safe", w.run("siwe.remove_unused"))
    check("failure is reported, not raised", w.run("siwe.merge_skinned") is False)


def test_input_popup_and_slider() -> None:
    """直接入力・右クリック入力の小窓と、ライブスライダー（ドラッグ全体が 1 回の Undo）を確認する。"""
    from PySide6.QtCore import QItemSelectionModel as S
    w = win()
    w.reload(force=True)
    base = mesh_io.read_weights(obj_(), [2])[2]
    sel = w.view.selectionModel()
    sel.clear()
    sel.select(w.model.index(2, 1), S.SelectionFlag.Select)

    # 数字の直接入力 → 小窓 → Enter で適用
    w.on_typed("7")
    popup = w._input_popup
    check("popup typed text", popup.box.lineEdit().text() == "7", popup.box.lineEdit().text())
    popup.box.lineEdit().setText("0.7")
    popup._accept()
    got = mesh_io.read_weights(obj_(), [2])[2]
    check("popup apply", abs(got["arm.L"] - 0.7) < 1e-4, str(got))
    bpy.ops.ed.undo()

    # 右クリック（Abs ではクリックしたセルの値が初期値）
    w.reload(force=True)
    sel = w.view.selectionModel()
    sel.clear()
    sel.select(w.model.index(2, 1), S.SelectionFlag.Select)
    w.open_input(clicked=w.model.index(2, 1))
    check("right click initial value", abs(w._input_popup.box.value() - 0.4) < 1e-4, str(w._input_popup.box.value()))
    w._input_popup.close()

    # ライブスライダー: 押す → 動かす → 戻す → 離す
    w.value_box.setValue(0.0)
    w.slider.sliderPressed.emit()
    w.slider.setValue(900)
    mid = mesh_io.read_weights(obj_(), [2])[2]
    check("slider live", abs(mid["arm.L"] - 0.9) < 1e-3, str(mid))
    w.slider.setValue(300)
    low = mesh_io.read_weights(obj_(), [2])[2]
    check("slider back", abs(low["arm.L"] - 0.3) < 1e-3 and abs(low["spine"] - 0.7) < 1e-3, str(low))
    w.slider.sliderReleased.emit()
    bpy.ops.ed.undo()
    after = mesh_io.read_weights(obj_(), [2])[2]
    check("slider is one undo step", abs(after["arm.L"] - base["arm.L"]) < 1e-4, str(after))
    w.reload(force=True)

    # 命名規則エディタとロック一括
    w.open_rule_editor()
    check("rule editor", w._rule_editor.isVisible())
    w._rule_editor.edit.setPlainText("_L,_R")
    w._rule_editor.applied.emit("_L,_R")
    check("rules applied", w.settings().mirror_rules == "_L,_R")
    w._rule_editor.close()
    w.lock_all(True)
    check("lock all", all(w.model.snap.locked))
    w.lock_all(False)
    check("unlock all", not any(w.model.snap.locked))


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


schedule([setup, test_table, test_apply, test_lock, test_header_double_click, test_edit_mode_undo, test_tools, test_input_popup_and_slider, shot,
          test_new_file_closes_window, test_unregister_closes_window, finish])
