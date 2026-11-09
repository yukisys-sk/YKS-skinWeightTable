"""Skin Weight Table の Qt ウィンドウ（Maya 版 SIWeightEditor の画面構成に近づけたもの）。

データの実体は ``WindowManager.siwe`` のまま、実際の処理は既存の ``siwe.*`` オペレーターに任せる。
このウィンドウは「表示（モデル）と操作（ボタン・入力欄）」だけを担当する。

注意:
    - ``exec()`` や ``QInputDialog.get*`` のような入れ子のイベントループは使わない（Blender が固まる）
    - bpy のオブジェクトはウィジェットに保持しない（File > Open 後に無効になる）。毎回名前で引く
"""

from __future__ import annotations

import bpy
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import table
from .model import Snapshot, VerticalHeader, WeightModel

POLL_MS = 150
FIXED_VALUES = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
# ウェイトを書き換えるオペレーター（実行後に Undo ステップを積む）
DATA_OPS = frozenset({
    "siwe.apply_input", "siwe.set_fixed", "siwe.lock", "siwe.round_off", "siwe.enforce_limit",
    "siwe.cell_paste", "siwe.vertex_paste", "siwe.move_influence", "siwe.smooth", "siwe.symmetrize",
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

        # --- 表
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.header = VerticalHeader(self.view)
        self.view.setHorizontalHeader(self.header)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.verticalHeader().setDefaultSectionSize(20)
        self.view.horizontalHeader().setDefaultSectionSize(48)
        self.view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Fixed)
        main.addWidget(self.view, 1)

        # --- 入力
        self.mode_group = QtWidgets.QButtonGroup(self)
        mode_buttons = []
        for key, label in (("ABS", "Abs"), ("ADD", "Add"), ("ADD_PERCENT", "Add%")):
            b = self._button(label, lambda _c=False, k=key: self.set_prop("input_mode", k), "", True)
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

        fixed = [self._button(f"{v:g}", lambda _c=False, v=v: self.apply_fixed(v)) for v in FIXED_VALUES]
        main.addLayout(self._row(*fixed))
        main.addLayout(self._row(
            self._button("Lock Wt", lambda: self.run("siwe.lock", sync=True, mode="LOCK"), "選択セルをロック"),
            self._button("Unlock Wt", lambda: self.run("siwe.lock", sync=True, mode="UNLOCK"), "選択セルをアンロック"),
            self._button("Clear locks", lambda: self.run("siwe.lock", mode="CLEAR"), "すべてのロックを解除"),
        ))
        self.statusBar().showMessage("")
        self.resize(760, 640)

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
