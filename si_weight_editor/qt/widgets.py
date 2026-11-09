"""表ビューと入力用の小さなウィンドウ（Maya 版の右クリック入力・直接入力・命名規則エディタに相当）。

入れ子のイベントループ（``exec()`` など）は Blender を固めるため使わない。ポップアップはすべて ``show()`` で出す。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal

NUMBER_KEYS = set("0123456789.-")


class WeightView(QtWidgets.QTableView):
    """数字キーの直接入力と、右クリックを通知するテーブルビュー。"""

    typed = Signal(str)
    right_clicked = Signal(QtCore.QPoint, bool)  # グローバル座標、Ctrl/Shift が押されているか

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """セル選択中に数字を打ち始めたら、入力小窓を開くよう通知する。"""
        mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        if event.text() and event.text() in NUMBER_KEYS and mods == Qt.KeyboardModifier.NoModifier:
            self.typed.emit(event.text())
            return
        super().keyPressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """右クリックはメニュー/入力小窓用に通知し、それ以外は通常どおり処理する。"""
        if event.button() == Qt.MouseButton.RightButton:
            ctrl = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            self.right_clicked.emit(event.globalPosition().toPoint(), ctrl)
            return
        super().mouseReleaseEvent(event)


class InputPopup(QtWidgets.QWidget):
    """セルへ値を入力する小さな枠なしウィンドウ（Enter で確定、Esc で閉じる）。"""

    accepted = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.box = QtWidgets.QDoubleSpinBox()
        self.box.setRange(-100.0, 100.0)
        self.box.setDecimals(3)
        self.box.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.box.setKeyboardTracking(False)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(self.box)
        self.box.lineEdit().returnPressed.connect(self._accept)
        self.setFixedWidth(90)

    def open_at(self, pos: QtCore.QPoint, value: float, typed: str = "") -> None:
        """指定位置に小窓を出す。

        Args:
            pos: 画面（グローバル）座標。
            value: 初期値。
            typed: 打ち始めた文字。指定すると、それを入力欄の内容にする。
        """
        self.box.setValue(value)
        self.move(pos)
        self.show()
        self.activateWindow()
        self.box.setFocus()
        if typed:
            self.box.lineEdit().setText(typed)
        else:
            self.box.selectAll()

    def _accept(self) -> None:
        """入力値を通知して閉じる。"""
        self.box.interpretText()
        self.accepted.emit(self.box.value())
        self.close()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Esc で閉じる。"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class SmoothSettings(QtWidgets.QWidget):
    """スムースの設定（適用率・繰り返し回数・0 を保つ・最大インフルエンス数に従う）を編集する小さなウィンドウ。

    値を変えるたびに ``changed(プロパティ名, 値)`` を通知する。閉じても値は ``WindowManager.siwe`` に残る。
    """

    changed = Signal(str, object)

    def __init__(self, amount: float, iterations: int, keep_zero: bool, obey_limit: bool, limit: int, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Smooth Settings")
        form = QtWidgets.QFormLayout(self)
        self.ratio = QtWidgets.QSpinBox()
        self.ratio.setRange(0, 100)
        self.ratio.setSuffix("%")
        self.ratio.setToolTip("適用率（100 で通常のスムースと同じ）")
        self.iterations = QtWidgets.QSpinBox()
        self.iterations.setRange(1, 50)
        self.iterations.setToolTip("繰り返し回数")
        self.keep_zero = QtWidgets.QCheckBox("元が 0 のインフルエンスは 0 のままにする")
        self.obey_limit = QtWidgets.QCheckBox(f"スムース後にインフルエンス数を {limit} 以下にする")
        self.obey_limit.setToolTip("Enforce Limit の値に従う（Maya 版の Obey Max Influences）")
        self.set_values(amount, iterations, keep_zero, obey_limit)
        for label, widget in (("Ratio", self.ratio), ("Iterations", self.iterations), ("", self.keep_zero), ("", self.obey_limit)):
            form.addRow(label, widget)
        self.ratio.valueChanged.connect(lambda v: self.changed.emit("smooth_amount", v / 100))
        self.iterations.valueChanged.connect(lambda v: self.changed.emit("smooth_iterations", v))
        self.keep_zero.toggled.connect(lambda v: self.changed.emit("smooth_keep_zero", bool(v)))
        self.obey_limit.toggled.connect(lambda v: self.changed.emit("smooth_obey_limit", bool(v)))

    def set_values(self, amount: float, iterations: int, keep_zero: bool, obey_limit: bool) -> None:
        """通知を出さずに表示を更新する（本体側で値が変わったとき用）。

        Args:
            amount: 適用率（0〜1）。
            iterations: 繰り返し回数。
            keep_zero: 0 を保つか。
            obey_limit: 最大インフルエンス数に従うか。
        """
        for w in (self.ratio, self.iterations, self.keep_zero, self.obey_limit):
            w.blockSignals(True)
        self.ratio.setValue(round(amount * 100))
        self.iterations.setValue(iterations)
        self.keep_zero.setChecked(keep_zero)
        self.obey_limit.setChecked(obey_limit)
        for w in (self.ratio, self.iterations, self.keep_zero, self.obey_limit):
            w.blockSignals(False)


class RuleEditor(QtWidgets.QWidget):
    """左右の命名規則（1 行に『左,右』）を編集する小さなウィンドウ。"""

    applied = Signal(str)

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Symmetry Naming Rules")
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("1 行に『左,右』。. は 1 文字のワイルドカード、\\. は . そのもの"))
        self.edit = QtWidgets.QPlainTextEdit(text)
        lay.addWidget(self.edit)
        row = QtWidgets.QHBoxLayout()
        apply_but = QtWidgets.QPushButton("Apply")
        apply_but.clicked.connect(lambda: self.applied.emit(self.edit.toPlainText()))
        close_but = QtWidgets.QPushButton("Close")
        close_but.clicked.connect(self.close)
        row.addWidget(apply_but)
        row.addWidget(close_but)
        lay.addLayout(row)
        self.resize(360, 260)
