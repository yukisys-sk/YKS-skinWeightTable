"""Skin Weight Table の Qt ウィンドウ（Maya 版 SIWeightEditor の画面構成に近づけたもの）。

データの実体は ``WindowManager.siwe`` のまま、実際の処理は既存の ``siwe.*`` オペレーターに任せる。
このウィンドウは「表示（モデル）と操作（ボタン・入力欄）」だけを担当する。

注意:
    - ``exec()`` や ``QInputDialog.get*`` のような入れ子のイベントループは使わない（Blender が固まる）
    - bpy のオブジェクトはウィジェットに保持しない（File > Open 後に無効になる）。毎回名前で引く
"""

from __future__ import annotations

from pathlib import Path

import bpy
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import table
from .. import mesh_io
from ..core import weight_math as wm
from .model import Snapshot, VerticalHeader, WeightModel
from .widgets import InputPopup, RuleEditor, SmoothSettings, WeightView

ICON_DIR = Path(__file__).parent / "icons"
# ボタンの文字ラベル。``icons/<キー>.png`` を置くと、そのボタンだけ文字の代わりに画像（自作のアイコン）を使う
BUTTON_LABELS = {
    "hummer": "Ham", "hummer_zero": "Ham0", "smooth": "Smo", "smooth_zero": "Smo0", "smooth_setting": "Smo…",
    "freeze": "Frz", "freeze_m": "FrzM",
    "simple_copy": "S.Copy", "simple_topology": "S.Idx", "simple_position": "S.Pos",
    "transfer_copy": "T.Copy", "transfer_paste": "T.Paste",
    "move_copy": "M.Copy", "move_paste": "M.Move",
    "vtx_copy": "V.Copy", "vtx_paste": "V.Paste",
    "cell_copy": "C.Copy", "cell_paste": "C.Paste",
    "sym_weight": "Sym", "auto_symmetry": "Auto", "marge": "Merge",
    "mute": "Mute", "bind_pose": "Bind", "go_export": "GoExp", "go_import": "GoImp",
    "inf_add": "+Inf", "inf_rem": "-Inf", "inf_clean": "Clean",
}
POLL_MS = 150
SLIDER_STEPS = 1000
LIVE_REFRESH_MS = 60
FIXED_VALUES = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
# ウェイトを書き換えるオペレーター（実行後に Undo ステップを積む）
DATA_OPS = frozenset({
    "siwe.apply_input", "siwe.set_fixed", "siwe.lock", "siwe.lock_column", "siwe.round_off", "siwe.enforce_limit",
    "siwe.cell_paste", "siwe.vertex_paste", "siwe.move_influence", "siwe.smooth", "siwe.symmetrize",
    "siwe.freeze", "siwe.auto_symmetry", "siwe.merge_skinned", "siwe.simple_paste", "siwe.transfer_paste",
    "siwe.add_influence", "siwe.remove_influence", "siwe.remove_unused", "siwe.go_import",
    "siwe.toggle_mute", "siwe.bind_pose",
})

STYLE = """
QPushButton { background: #444; color: #ddd; border: 1px solid #b4b4b4; padding: 1px 6px; min-height: 18px; }
QPushButton:hover { background: #727272; }
QPushButton:checked { background: #5b7fa8; }
QTableView { gridline-color: #444; background: #2b2b2b; color: #d2d2d2; selection-background-color: #5285a6; }
QSpinBox, QDoubleSpinBox { min-height: 18px; }
"""


def _override() -> dict | None:
    """オペレーターを呼ぶためのコンテキスト（3D ビューのあるウィンドウ・エリア・リージョン）を返す。

    Returns:
        ``temp_override`` に渡す辞書。3D ビューが無ければ None。
    """
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                if region is not None:
                    return {"window": win, "area": area, "region": region}
    return None


def redraw_blender() -> None:
    """3D ビューとプロパティエディタを再描画する（タイマーからの変更は自動で再描画されないため）。"""
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in {"VIEW_3D", "PROPERTIES"}:
                area.tag_redraw()


class SkinWeightWindow(QtWidgets.QMainWindow):
    """Skin Weight Table のメインウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Skin Weight Table")
        self.setStyleSheet(STYLE)
        self.model = WeightModel(self)
        self.buttons: dict[str, QtWidgets.QPushButton] = {}
        self._build_ui()
        self.reload()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)

    # ------------------------------------------------------------------ UI 構築
    def _button(self, text: str, slot, tip: str = "", checkable: bool = False, width: int | None = None):
        """フラットなボタンを作る。

        Args:
            text: ボタン名。
            slot: クリック時の呼び出し先。
            tip: ツールチップ。
            checkable: トグルボタンにするか。
            width: 固定幅（px）。None なら内容に合わせる。

        Returns:
            ``QPushButton``。
        """
        b = QtWidgets.QPushButton(text)
        b.setCheckable(checkable)
        b.setToolTip(tip)
        if width:
            b.setFixedWidth(width)
        b.clicked.connect(slot)
        return b

    def _row(self, *widgets, spacing: int = 0) -> QtWidgets.QHBoxLayout:
        """ウィジェットを横に並べたレイアウトを返す。

        Args:
            *widgets: 並べるウィジェット。
            spacing: 間隔（px）。

        Returns:
            ``QHBoxLayout``。
        """
        lay = QtWidgets.QHBoxLayout()
        lay.setSpacing(spacing)
        lay.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            lay.addWidget(w)
        return lay

    def _build_ui(self) -> None:
        """ツールバー・表・入力欄を組み立てる。"""
        s = table.settings(bpy.context)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main = QtWidgets.QVBoxLayout(central)
        main.setSpacing(4)

        # --- 上段ツールバー（Maya 版の並び: 表示 / 不正 / アイコン / 制限・桁数）
        self.show_but = self._button("Show", self.show_selected, "選択セルのみ表示")
        self.show_all_but = self._button("Show All", self.show_all, "すべてのセルを表示")
        self.filter_but = self._button("Filter", self.toggle_filter, "合計 0 のインフルエンスを隠す", True)
        self.filter_but.setChecked(s.filter_zero)
        self.joint_but = self._button("Joint Hilite", lambda: self.run("siwe.select_bones"), "選択セルのボーンを選択", False)
        main.addLayout(self._row(self.show_but, self.show_all_but, self.filter_but, self.joint_but))

        self.show_bad_but = self._button("Show Bad", lambda: self.run("siwe.select_bad_rows"), "不正なウェイトの頂点を選択")
        self.bad_group = QtWidgets.QButtonGroup(self)
        bad_buttons = []
        for key, label in (("UNDER", "Under Wt"), ("OVER", "Over Wt"), ("LIMIT", "Influences")):
            b = self._button(label, lambda _c=False, k=key: self.set_bad_filter(k), "", True)
            self.bad_group.addButton(b)
            b.setProperty("key", key)
            bad_buttons.append(b)
        self.bad_group.setExclusive(False)
        main.addLayout(self._row(self.show_bad_but, *bad_buttons))

        self.lock_ui_but = self._button("Lk", self.toggle_lock_ui, "表示メッシュのロック（選択変更を反映しない）", True, 28)
        self.cycle_but = self._button("⟳", lambda: self.reload(force=True), "現在の選択を反映", False, 28)
        self.clear_but = self._button("C", lambda: self.run("siwe.clear_table"), "表示のクリア", False, 28)
        self.adjust_but = self._button("⇄", lambda: self.run("siwe.select_from_cells", sync=True), "セル選択から頂点を選択", False, 28)
        self.w1_but = self._button("0-1", lambda: self.set_scale("1"), "ウェイトを 0〜1 で表示", True, 40)
        self.w100_but = self._button("0-100", lambda: self.set_scale("100"), "ウェイトを 0〜100 で表示", True, 52)
        scale_group = QtWidgets.QButtonGroup(self)
        scale_group.addButton(self.w1_but)
        scale_group.addButton(self.w100_but)
        (self.w1_but if s.display_scale == "1" else self.w100_but).setChecked(True)
        main.addLayout(self._row(self.lock_ui_but, self.cycle_but, self.clear_but, self.adjust_but, self.w1_but, self.w100_but))

        self.limit_box = QtWidgets.QSpinBox()
        self.limit_box.setRange(1, 32)
        self.limit_box.setValue(s.limit)
        self.limit_box.setToolTip("1 頂点あたりの最大インフルエンス数")
        self.limit_box.valueChanged.connect(lambda v: self.set_prop("limit", v, reload=True))
        self.digit_box = QtWidgets.QSpinBox()
        self.digit_box.setRange(0, 8)
        self.digit_box.setValue(s.digits)
        self.digit_box.valueChanged.connect(lambda v: self.set_prop("digits", v, reload=True))
        enforce = self._button("Enforce Limit", lambda: self.run("siwe.enforce_limit"), "インフルエンス数を制限して正規化")
        round_but = self._button("Round Off", lambda: self.run("siwe.round_off"), "表示桁数で四捨五入")
        main.addLayout(self._row(enforce, self.limit_box, QtWidgets.QLabel(" Digits "), self.digit_box, round_but, spacing=4))

        self._build_tools(main)
        self._wire_context_menus()

        # --- 表
        self.view = WeightView()
        self.view.setModel(self.model)
        self.header = VerticalHeader(self.view)
        self.view.setHorizontalHeader(self.header)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.verticalHeader().setDefaultSectionSize(20)
        self.view.horizontalHeader().setDefaultSectionSize(48)
        self.view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)
        main.addWidget(self.view, 1)
        self.view.typed.connect(self.on_typed)
        self.view.right_clicked.connect(self.on_right_click)
        self.header.sectionDoubleClicked.connect(self.on_header_double_clicked)
        self.header.right_clicked.connect(self.on_header_right_clicked)

        # --- 入力
        self.mode_group = QtWidgets.QButtonGroup(self)
        mode_buttons = []
        for key, label in (("ABS", "Abs"), ("ADD", "Add"), ("ADD_PERCENT", "Add%")):
            b = self._button(label, lambda _c=False, k=key: self.set_input_mode(k), "", True)
            self.mode_group.addButton(b)
            b.setProperty("key", key)
            if s.input_mode == key:
                b.setChecked(True)
            mode_buttons.append(b)
        self.norm_but = self._button("Normalize", lambda c: self.set_prop("normalize", bool(c)), "入力後に合計を 1.0 へ正規化", True)
        self.norm_but.setChecked(s.normalize)
        self.unlimited_but = self._button("Unlimited", lambda c: self.set_prop("unlimited", bool(c)), "合計 1.0 超を許容", True)
        self.unlimited_but.setChecked(s.unlimited)
        main.addLayout(self._row(*mode_buttons, self.norm_but, self.unlimited_but))

        self.value_box = QtWidgets.QDoubleSpinBox()
        self.value_box.setRange(-100.0, 100.0)
        self.value_box.setDecimals(3)
        self.value_box.setValue(s.value)
        self.value_box.setSingleStep(0.05)
        self.value_box.valueChanged.connect(lambda v: self.set_prop("value", v))
        apply_but = self._button("Apply", self.apply, "選択セルへ入力値を適用")
        self.value_box.setKeyboardTracking(False)
        main.addLayout(self._row(self.value_box, apply_but, spacing=4))
        self._live = None
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.timeout.connect(self._live_refresh)
        self.slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.slider.setToolTip("ライブスライダー（ドラッグ中に選択セルへ反映。離すと 1 回の Undo ステップになる）")
        self.slider.sliderPressed.connect(self.live_begin)
        self.slider.valueChanged.connect(self.live_update)
        self.slider.sliderReleased.connect(self.live_end)
        self.update_slider_range()
        main.addWidget(self.slider)

        fixed = [self._button(f"{v:g}", lambda _c=False, v=v: self.apply_fixed(v)) for v in FIXED_VALUES]
        main.addLayout(self._row(*fixed))
        lock_but = self._button("Lock Wt", lambda: self.run("siwe.lock", sync=True, mode="LOCK"), "選択セルをロック（右クリックで全セル）")
        unlock_but = self._button("Unlock Wt", lambda: self.run("siwe.lock", sync=True, mode="UNLOCK"), "選択セルをアンロック（右クリックで全セル）")
        for b, flag in ((lock_but, True), (unlock_but, False)):
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _p, f=flag: self.lock_all(f))
        main.addLayout(self._row(
            lock_but, unlock_but,
            self._button("Clear locks", lambda: self.run("siwe.lock", mode="CLEAR"), "すべてのロックを解除"),
        ))
        self.statusBar().showMessage("")
        self.resize(760, 640)

    def icon_button(self, key: str, tip: str, slot) -> QtWidgets.QPushButton:
        """サブツールのボタンを作る。文字ラベルが基本で、``icons/<key>.png`` があればそれをアイコンにする。

        Args:
            key: ボタンの識別キー（``BUTTON_LABELS`` のキー、アイコンのファイル名）。
            tip: ツールチップ（機能名）。
            slot: クリック時の呼び出し先。

        Returns:
            ``QPushButton``。
        """
        icon_path = ICON_DIR / f"{key}.png"
        if icon_path.exists():
            b = QtWidgets.QPushButton()
            b.setIcon(QtGui.QIcon(str(icon_path)))
            b.setIconSize(QtCore.QSize(22, 22))
            b.setFixedSize(30, 28)
        else:
            b = QtWidgets.QPushButton(BUTTON_LABELS.get(key, key))
            b.setMinimumWidth(40)
            b.setFixedHeight(26)
        b.setToolTip(tip)
        b.clicked.connect(slot)
        self.buttons[key] = b
        return b

    def _build_tools(self, main: QtWidgets.QVBoxLayout) -> None:
        """サブツールのボタン列（Maya 版の 3 行の並び）を作る。

        Args:
            main: 追加先のレイアウト。
        """
        s = table.settings(bpy.context)

        def op(op_id: str, sync: bool = False, **kw):
            """オペレーターを実行するスロットを返す。"""
            return lambda *_: self.run(op_id, sync=sync, **kw)

        def row(*groups) -> QtWidgets.QHBoxLayout:
            """グループ（ボタンのリスト）の間に隙間を空けて 1 行にする。"""
            lay = QtWidgets.QHBoxLayout()
            lay.setSpacing(0)
            lay.setContentsMargins(0, 0, 0, 0)
            for i, group in enumerate(groups):
                if i:
                    lay.addSpacing(10)
                for w in group:
                    lay.addWidget(w)
            lay.addStretch(1)
            return lay

        ib = self.icon_button
        # 1 行目: ハンマー / スムース / 比率 / Freeze
        self.ratio_box = QtWidgets.QSpinBox()
        self.ratio_box.setRange(0, 100)
        self.ratio_box.setSuffix("%")
        self.ratio_box.setValue(round(s.smooth_amount * 100))
        self.ratio_box.setToolTip("スムース/ハンマーの適用率（100 で通常のスムースと同じ）")
        self.ratio_box.valueChanged.connect(lambda v: (self.set_prop("smooth_amount", v / 100), self.sync_smooth_settings()))
        self.iter_box = QtWidgets.QSpinBox()
        self.iter_box.setRange(1, 50)
        self.iter_box.setValue(s.smooth_iterations)
        self.iter_box.setPrefix("x")
        self.iter_box.setToolTip("スムースの繰り返し回数")
        self.iter_box.valueChanged.connect(lambda v: (self.set_prop("smooth_iterations", v), self.sync_smooth_settings()))
        main.addLayout(row(
            [ib("hummer", "Weight Hammer", op("siwe.smooth", sync=True, hammer=True)),
             ib("hummer_zero", "Weight Hammer（ウェイト 0 のセルを変更しない）", op("siwe.smooth", sync=True, hammer=True, keep_zero=True))],
            [ib("smooth", "Weight Smooth", op("siwe.smooth", sync=True)),
             ib("smooth_zero", "Weight Smooth（ウェイト 0 のセルを変更しない）", op("siwe.smooth", sync=True, keep_zero=True)),
             ib("smooth_setting", "スムース設定を開く", self.open_smooth_settings)],
            [self.ratio_box, self.iter_box],
            [ib("freeze", "Freeze（モディファイアを適用しスキニングを外す）", op("siwe.freeze", keep_skin=False)),
             ib("freeze_m", "Freeze_M（モディファイアを適用しスキニングを残す）", op("siwe.freeze", keep_skin=True))],
        ))
        # 2 行目: コピー / ペースト系
        main.addLayout(row(
            [ib("simple_copy", "Simple Weight Copy", op("siwe.simple_copy")),
             ib("simple_topology", "Simple Weight Paste（Name Index）", op("siwe.simple_paste", method="INDEX")),
             ib("simple_position", "Simple Weight Paste（Name Position）", op("siwe.simple_paste", method="POSITION"))],
            [ib("transfer_copy", "Transfer Weight / Copy", op("siwe.transfer_copy")),
             ib("transfer_paste", "Transfer Weight / Paste", op("siwe.transfer_paste"))],
            [ib("move_copy", "Move Influence Weight / Copy（移動元の列）", op("siwe.move_influence", sync=True, step="COPY")),
             ib("move_paste", "Move Influence Weight / Paste（選択列へ移動）", op("siwe.move_influence", sync=True, step="PASTE"))],
            [ib("vtx_copy", "Vertex Weight Copy", op("siwe.vertex_copy")),
             ib("vtx_paste", "Vertex Weight Paste", op("siwe.vertex_paste"))],
            [ib("cell_copy", "Cell Copy", op("siwe.cell_copy", sync=True)),
             ib("cell_paste", "Cell Paste", op("siwe.cell_paste", sync=True))],
        ))
        # 3 行目: 対称 / スキン状態 / Go / インフルエンス管理
        self.axis_box = QtWidgets.QComboBox()
        self.axis_box.addItems(["X", "Y", "Z"])
        self.axis_box.setCurrentText(s.mirror_axis)
        self.axis_box.setToolTip("ミラー軸")
        self.axis_box.currentTextChanged.connect(lambda v: self.set_prop("mirror_axis", v))
        self.dir_box = QtWidgets.QComboBox()
        self.dir_box.addItem("+ → -", "POS_TO_NEG")
        self.dir_box.addItem("- → +", "NEG_TO_POS")
        self.dir_box.setCurrentIndex(0 if s.mirror_direction == "POS_TO_NEG" else 1)
        self.dir_box.setToolTip("ウェイトを転送する向き")
        self.dir_box.currentIndexChanged.connect(lambda i: self.set_prop("mirror_direction", self.dir_box.itemData(i)))
        self.influence_edit = QtWidgets.QLineEdit(s.new_influence)
        self.influence_edit.setPlaceholderText("influence")
        self.influence_edit.setFixedWidth(90)
        self.influence_edit.setToolTip("追加するインフルエンス名（空ならメッシュと一緒に選択したアーマチュアの選択ボーン）")
        self.influence_edit.textChanged.connect(lambda v: self.set_prop("new_influence", v))
        main.addLayout(row(
            [self.axis_box, self.dir_box,
             ib("sym_weight", "Weight Symmetrize", op("siwe.symmetrize")),
             ib("auto_symmetry", "Auto Symmetry", op("siwe.auto_symmetry")),
             ib("marge", "Mesh Merge with Skinning", op("siwe.merge_skinned"))],
            [ib("mute", "Toggle Mute Skinning", op("siwe.toggle_mute")),
             ib("bind_pose", "Go to Bind Pose", op("siwe.bind_pose"))],
            [ib("go_export", "Go Export", op("siwe.go_export")),
             ib("go_import", "Go Import", op("siwe.go_import"))],
            [self.influence_edit,
             ib("inf_add", "Add Influence", op("siwe.add_influence")),
             ib("inf_rem", "Remove Influence（選択列）", self.confirm_remove_influence),
             ib("inf_clean", "Remove Unused Influences", op("siwe.remove_unused"))],
        ))

    def _wire_context_menus(self) -> None:
        """Symmetry 系ボタンの右クリックで、命名規則エディタを開く。"""
        for key in ("sym_weight", "auto_symmetry"):
            b = self.buttons[key]
            b.setToolTip(b.toolTip() + "（右クリックで命名規則）")
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(self.open_rule_editor)

    def set_input_mode(self, key: str) -> None:
        """入力モードを切り替え、スライダーの範囲も合わせる。

        Args:
            key: ``ABS`` / ``ADD`` / ``ADD_PERCENT``。
        """
        self.set_prop("input_mode", key)
        self.update_slider_range()

    def confirm_remove_influence(self, *_args) -> None:
        """選択列のインフルエンスを、確認してから削除する（入れ子のイベントループを避けるため非モーダル）。"""
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Icon.Question, "Remove Influence",
                                    "選択した列のインフルエンス（頂点グループ）を削除しますか？", parent=self)
        box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        box.finished.connect(lambda r: self.run("siwe.remove_influence", sync=True)
                             if r == QtWidgets.QMessageBox.StandardButton.Yes.value else None)
        box.open()
        self._confirm_box = box

    # ------------------------------------------------------------------ 直接入力 / 右クリック
    def _cursor_pos(self) -> QtCore.QPoint:
        """マウスカーソルの画面位置を返す（入力小窓の表示位置）。

        Returns:
            グローバル座標。
        """
        return QtGui.QCursor.pos()

    def open_input(self, pos: QtCore.QPoint | None = None, typed: str = "", clicked=None) -> None:
        """セルへ値を入れる小窓を開く。Enter で、入力欄の値として適用する。

        Args:
            pos: 表示位置。None ならマウスカーソルの位置。
            typed: 打ち始めた文字。
            clicked: 右クリックされたセルの ``QModelIndex``。Abs モードではその値を初期値にする。
        """
        s = self.settings()
        if not self.view.selectionModel().selectedIndexes():
            self.message("セルが選択されていません")
            return
        initial = 0.0
        if clicked is not None and clicked.isValid() and s.input_mode == "ABS":
            initial = self.model.snap.values[self.model.cell_index(clicked.row(), clicked.column())] * float(s.display_scale)
        self._input_popup = InputPopup(self)
        self._input_popup.accepted.connect(self._on_input_accepted)
        self._input_popup.open_at(pos or self._cursor_pos(), initial, typed)

    def _on_input_accepted(self, value: float) -> None:
        """入力小窓で確定した値を、入力欄に入れて適用する。

        Args:
            value: 入力された値（表示スケール）。
        """
        self.value_box.setValue(value)
        self.apply()

    def on_header_double_clicked(self, section: int) -> None:
        """見出しのダブルクリック: その列のロックを全頂点について切り替える（Maya 版と同じ）。

        Args:
            section: 表示上の列番号。実際の列番号（``cols`` の添字）へ変換して渡す。
        """
        column = self.model.source_column(section)
        self.view.clearSelection()
        if column is not None:
            self.run("siwe.lock_column", column=column)

    def on_header_right_clicked(self, section: int) -> None:
        """見出しの右クリック: その列のボーンをアーマチュア上で選択する（Maya 版と同じ）。

        Args:
            section: 表示上の列番号。見出しの外（-1）なら何もしない。
        """
        column = self.model.source_column(section)
        if column is not None:
            self.run("siwe.select_bones", column=column)

    def on_typed(self, char: str) -> None:
        """セル選択中に数字を打ち始めたとき、入力小窓を開く。

        Args:
            char: 打った文字。
        """
        self.open_input(typed=char)

    def on_right_click(self, pos: QtCore.QPoint, ctrl: bool) -> None:
        """表の右クリック: 通常は入力小窓、Ctrl/Shift 付きならセルコピー/ペーストのメニュー。

        Args:
            pos: 画面（グローバル）座標。
            ctrl: Ctrl または Shift が押されているか。
        """
        index = self.view.indexAt(self.view.viewport().mapFromGlobal(pos))
        sel = self.view.selectionModel()
        if index.isValid() and not sel.isSelected(index):
            sel.select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        if ctrl:
            menu = QtWidgets.QMenu(self)
            menu.addAction("Cell Copy", lambda: self.run("siwe.cell_copy", sync=True))
            menu.addAction("Cell Paste", lambda: self.run("siwe.cell_paste", sync=True))
            menu.popup(pos)
            self._menu = menu
            return
        self.open_input(pos=pos, clicked=index)

    # ------------------------------------------------------------------ ライブスライダー
    def _slider_range(self) -> tuple[int, int]:
        """入力モードに合わせたスライダーの範囲（整数）を返す。

        Returns:
            ``(最小, 最大)``。Abs は 0〜1000、Add 系は ±1000。
        """
        return (0, SLIDER_STEPS) if self.settings().input_mode == "ABS" else (-SLIDER_STEPS, SLIDER_STEPS)

    def update_slider_range(self) -> None:
        """スライダーの範囲を、入力モードに合わせて更新する（値は 0 に戻す）。"""
        lo, hi = self._slider_range()
        self.slider.blockSignals(True)
        self.slider.setRange(lo, hi)
        self.slider.setValue(0)
        self.slider.blockSignals(False)

    def _slider_to_value(self, pos: int) -> float:
        """スライダー位置を、表示スケールの入力値へ換算する。

        Args:
            pos: スライダーの整数位置。

        Returns:
            表示スケールの値（0.0〜``display_scale``）。
        """
        return pos / SLIDER_STEPS * float(self.settings().display_scale)

    def live_begin(self) -> None:
        """スライダーを押した瞬間に、選択セルの元のウェイトを記録する（動かして戻しても正しく計算できる）。"""
        s = self.settings()
        obj = table.active_mesh(bpy.context)
        if obj is None:
            self._live = None
            return
        self.sync_selection()
        by_row: dict[int, list[int]] = {}
        for r, c in table.selected_cells(s):
            by_row.setdefault(r, []).append(c)
        if not by_row:
            self.message("セルが選択されていません")
            self._live = None
            return
        names = [c.name for c in s.cols]
        verts = {r: s.rows[r].vert for r in by_row}
        orig = mesh_io.read_weights(obj, list(verts.values()))
        nc = len(names)
        flags = table.cell_flags(s, "locked")
        self._live = {
            "object": obj.name,
            "names": names,
            "rows": {
                r: {
                    "vert": verts[r],
                    "cols": cols,
                    "orig": [orig[verts[r]].get(n, 0.0) for n in names],
                    "locked": {c for c in range(nc) if flags[r * nc + c]},
                }
                for r, cols in by_row.items()
            },
        }

    def live_update(self, pos: int) -> None:
        """スライダー移動中: 記録した元の値から計算し直して書き込む（Undo は積まない）。

        Args:
            pos: スライダーの整数位置。
        """
        live = self._live
        if live is None:
            return
        s = self.settings()
        shown = self._slider_to_value(pos)
        self.value_box.blockSignals(True)
        self.value_box.setValue(shown)
        self.value_box.blockSignals(False)
        value = shown / float(s.display_scale)
        obj = bpy.data.objects.get(live["object"])
        if obj is None:
            return
        out = {}
        for r, info in live["rows"].items():
            edited = wm.apply_input(info["orig"], info["cols"], info["locked"], s.input_mode, value, s.unlimited)
            new, bake = wm.normalize_row(edited, info["orig"], info["cols"], info["locked"], force=s.normalize, unlimited=s.unlimited)
            new = new if bake else info["orig"]
            out[info["vert"]] = dict(zip(live["names"], new))
        mesh_io.write_weights(obj, out)
        redraw_blender()
        self._live_dirty = True
        if not self._live_timer.isActive():
            self._live_timer.start(LIVE_REFRESH_MS)

    def _live_refresh(self) -> None:
        """スライダー移動中の表の更新（頻度を抑える）。"""
        table.refresh(bpy.context)
        self.reload()

    def live_end(self) -> None:
        """スライダーを離したとき: 表を更新し、ドラッグ全体を 1 回の Undo ステップにする。"""
        if self._live is None:
            return
        self._live_timer.stop()
        self._live = None
        table.refresh(bpy.context)
        self.reload()
        bpy.ops.ed.undo_push(message="Weight Slider")
        self.slider.blockSignals(True)
        self.slider.setValue(0)
        self.slider.blockSignals(False)

    # ------------------------------------------------------------------ 命名規則・ロック
    def open_rule_editor(self, *_args) -> None:
        """左右の命名規則エディタを開く（Symmetry ボタンの右クリック）。"""
        self._rule_editor = RuleEditor(self.settings().mirror_rules, self)
        self._rule_editor.applied.connect(lambda text: self.set_prop("mirror_rules", text))
        self._rule_editor.show()

    def open_smooth_settings(self, *_args) -> None:
        """スムース設定ウィンドウを開く（開いていれば前面に出す）。"""
        existing = getattr(self, "_smooth_settings", None)
        if existing is not None and existing.isVisible():
            self.sync_smooth_settings()
            existing.raise_()
            return
        s = self.settings()
        self._smooth_settings = SmoothSettings(s.smooth_amount, s.smooth_iterations, s.smooth_keep_zero, s.smooth_obey_limit, s.limit, self)
        self._smooth_settings.changed.connect(self.on_smooth_setting_changed)
        self._smooth_settings.show()

    def on_smooth_setting_changed(self, name: str, value) -> None:
        """設定ウィンドウでの変更を反映し、ツールバーの率・回数の表示も合わせる。

        Args:
            name: ``WindowManager.siwe`` のプロパティ名。
            value: 新しい値。
        """
        self.set_prop(name, value)
        s = self.settings()
        for box, v in ((self.ratio_box, round(s.smooth_amount * 100)), (self.iter_box, s.smooth_iterations)):
            box.blockSignals(True)
            box.setValue(v)
            box.blockSignals(False)

    def sync_smooth_settings(self) -> None:
        """ツールバー側で率・回数を変えたとき、開いている設定ウィンドウの表示を合わせる。"""
        win = getattr(self, "_smooth_settings", None)
        if win is not None and win.isVisible():
            s = self.settings()
            win.set_values(s.smooth_amount, s.smooth_iterations, s.smooth_keep_zero, s.smooth_obey_limit)

    def lock_all(self, lock: bool) -> None:
        """全セルをロック/アンロックする（Lock Wt / Unlock Wt ボタンの右クリック）。

        Args:
            lock: True でロック、False でアンロック。
        """
        self.view.selectAll()
        self.run("siwe.lock", sync=True, mode="LOCK" if lock else "UNLOCK")

    # ------------------------------------------------------------------ 状態
    def settings(self):
        """UI 設定を返す。

        Returns:
            ``WindowManager.siwe``。
        """
        return table.settings(bpy.context)

    def message(self, text: str) -> None:
        """ステータスバーに文言を出す。

        Args:
            text: 表示する文言。
        """
        self.statusBar().showMessage(text, 8000)

    def reload(self, force: bool = False) -> None:
        """表を再読み込みする（選択を維持する）。

        Args:
            force: True なら ``table.refresh`` を呼んで選択を取り直す。
        """
        if force:
            table.refresh(bpy.context)
        s = self.settings()
        selected = self._selected_pairs()
        self.model.reload(Snapshot.read(s), table.generation)
        self._restore_selection(selected)
        title = "Skin Weight Table"
        if s.object_name:
            title += f" - {s.object_name}"
        self.setWindowTitle(title)

    def _poll(self) -> None:
        """Blender 側でテーブルが更新されていたら、モデルを読み直す。"""
        try:
            if table.generation != self.model.generation:
                self.reload()
        except ReferenceError:
            self.close()

    # ------------------------------------------------------------------ 選択の同期
    def _selected_pairs(self) -> set[tuple[int, int]]:
        """選択中のセルを ``(頂点, ボーン名の添字)`` の集合で返す（再読み込み後の復元用）。

        Returns:
            ``{(行番号, 列番号)}``（スナップショットの行・列）。
        """
        pairs = set()
        for idx in self.view.selectionModel().selectedIndexes():
            if idx.row() < len(self.model.rows) and idx.column() < len(self.model.cols):
                pairs.add(self.model.source_cell(idx.row(), idx.column()))
        return pairs

    def _restore_selection(self, pairs: set[tuple[int, int]]) -> None:
        """再読み込み前の選択セルを、同じ行・列にあれば選び直す。

        Args:
            pairs: ``_selected_pairs`` の結果。
        """
        if not pairs:
            return
        row_pos = {r: i for i, r in enumerate(self.model.rows)}
        col_pos = {c: i for i, c in enumerate(self.model.cols)}
        sel = self.view.selectionModel()
        for r, c in pairs:
            if r in row_pos and c in col_pos:
                sel.select(self.model.index(row_pos[r], col_pos[c]), QtCore.QItemSelectionModel.SelectionFlag.Select)

    def sync_selection(self) -> None:
        """Qt 上の選択セルを ``WindowManager.siwe`` のセル選択へ書き込む（既存オペレーターが参照する）。"""
        s = self.settings()
        nc = len(s.cols)
        flags = [False] * len(s.cells)
        for idx in self.view.selectionModel().selectedIndexes():
            r, c = self.model.source_cell(idx.row(), idx.column())
            flags[r * nc + c] = True
        if flags:
            s.cells.foreach_set("selected", flags)

    # ------------------------------------------------------------------ 操作
    def run(self, op_id: str, sync: bool = False, **kwargs) -> bool:
        """``siwe.*`` オペレーターを 3D ビューのコンテキストで実行し、表を更新する。

        Args:
            op_id: ``"siwe.lock"`` のようなオペレーター ID。
            sync: True なら実行前に Qt の選択セルを書き込む。
            **kwargs: オペレーターのプロパティ。

        Returns:
            実行できたら True。失敗は原因をステータスバーに出す。
        """
        ctx = _override()
        if ctx is None:
            self.message("3D ビューが見つかりません。3D ビューのあるウィンドウを開いてください")
            return False
        try:
            if sync:
                self.sync_selection()
            group, name = op_id.split(".")
            operator = getattr(getattr(bpy.ops, group), name)
            with bpy.context.temp_override(**ctx):
                result = operator(**kwargs)
                # タイマー（イベントループ）から呼んだオペレーターは Undo ステップを積まないため、
                # データを変更するものは明示的に積む
                if "FINISHED" in result and op_id in DATA_OPS:
                    bpy.ops.ed.undo_push(message=operator.get_rna_type().name)
        except RuntimeError as exc:
            self.message(str(exc).strip().splitlines()[-1] if str(exc).strip() else "実行できませんでした")
            return False
        redraw_blender()
        self.reload()
        return "FINISHED" in result

    def apply(self) -> None:
        """入力欄の値を選択セルへ適用する。"""
        self.run("siwe.apply_input", sync=True)

    def apply_fixed(self, value: float) -> None:
        """固定値ボタン: 入力欄に値を入れて即適用する。

        Args:
            value: 0〜1 の値。
        """
        s = self.settings()
        self.value_box.setValue(value * float(s.display_scale))
        self.run("siwe.set_fixed", sync=True, value=value)

    def set_prop(self, name: str, value, reload: bool = False) -> None:
        """UI 設定のプロパティを変更する。

        Args:
            name: プロパティ名。
            value: 新しい値。
            reload: True なら変更後に表を読み直す。
        """
        setattr(self.settings(), name, value)
        if reload:
            self.reload(force=name in {"filter_zero"})

    def set_scale(self, scale: str) -> None:
        """表示スケール（0-1 / 0-100）を切り替え、入力欄の値も換算する。

        Args:
            scale: ``"1"`` または ``"100"``。
        """
        s = self.settings()
        if s.display_scale == scale:
            return
        raw = self.value_box.value() / float(s.display_scale)
        s.display_scale = scale
        self.value_box.setValue(raw * float(scale))
        self.reload()

    def toggle_filter(self, checked: bool) -> None:
        """0 のインフルエンスを隠す/表示する。

        Args:
            checked: 隠すなら True。
        """
        self.set_prop("filter_zero", bool(checked))
        self.reload(force=True)

    def toggle_lock_ui(self, checked: bool) -> None:
        """選択変更をテーブルに反映するかを切り替える。

        Args:
            checked: 反映を止めるなら True。
        """
        self.set_prop("lock_ui", bool(checked))

    def set_bad_filter(self, key: str) -> None:
        """不正ウェイトの絞り込みを切り替える（同じものをもう一度押すと解除）。

        Args:
            key: ``UNDER`` / ``OVER`` / ``LIMIT``。
        """
        s = self.settings()
        s.bad_filter = "ALL" if s.bad_filter == key else key
        for b in self.bad_group.buttons():
            b.setChecked(b.property("key") == s.bad_filter)
        self.reload()

    def show_selected(self) -> None:
        """選択セルの列だけを表示する。"""
        self.run("siwe.show_cells", sync=True, all=False)

    def show_all(self) -> None:
        """すべての列を表示する。"""
        self.run("siwe.show_cells", all=True)
        self.filter_but.setChecked(False)

    def closeEvent(self, event) -> None:
        """タイマーを止めてから閉じる。"""
        self._timer.stop()
        super().closeEvent(event)
