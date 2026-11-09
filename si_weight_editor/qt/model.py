"""Qt のテーブルモデルと、ボーン名を縦書きにするヘッダー（Maya 版 SIWeightEditor を参考に PySide6 へ移植）。

モデルは ``table.refresh`` で作られる ``WindowManager.siwe`` の内容を、リフレッシュごとに
Python のリストへ一括で写して持つ（``data()`` は再描画のたびに全セル分呼ばれ、RNA のランダム
アクセスは極端に遅いため、``data()`` の中では bpy に触れない）。
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

EPS = 1e-6

# Maya 版の配色
JOINT_COLORS = [
    (161, 105, 48), (159, 161, 48), (104, 161, 48), (48, 161, 93),
    (48, 161, 161), (48, 103, 161), (111, 48, 161), (161, 48, 105),
]
V_HEADER_BG = (100, 100, 100)
UNDER_WEIGHT = (230, 54, 54)
OVER_WEIGHT = (210, 116, 32)
OVER_INFLUENCE = (210, 190, 40)
LOCK_BG = (100, 100, 100)
LOCK_TEXT = (160, 160, 160)
ZERO_DARKEN = 70


class Snapshot:
    """``WindowManager.siwe`` の内容を写し取ったもの（bpy 非依存）。"""

    def __init__(self) -> None:
        self.object_name = ""
        self.verts: list[int] = []
        self.totals: list[float] = []
        self.counts: list[int] = []
        self.col_names: list[str] = []
        self.col_visible: list[bool] = []
        self.values: list[float] = []
        self.locked: list[bool] = []
        self.scale = 1.0
        self.digits = 3
        self.limit = 4
        self.bad_filter = "ALL"
        self.dim_zero = True

    @classmethod
    def read(cls, s) -> "Snapshot":
        """UI 設定から一括でスナップショットを作る。

        Args:
            s: ``WindowManager.siwe``。

        Returns:
            ``Snapshot``。
        """
        snap = cls()
        snap.object_name = s.object_name
        nr, nc = len(s.rows), len(s.cols)
        snap.verts = [0] * nr
        snap.totals = [0.0] * nr
        snap.counts = [0] * nr
        if nr:
            s.rows.foreach_get("vert", snap.verts)
            s.rows.foreach_get("total", snap.totals)
            s.rows.foreach_get("count", snap.counts)
        snap.col_names = [c.name for c in s.cols]
        snap.col_visible = [True] * nc
        if nc:
            s.cols.foreach_get("visible", snap.col_visible)
        n = len(s.cells)
        snap.values = [0.0] * n
        snap.locked = [False] * n
        if n:
            s.cells.foreach_get("value", snap.values)
            s.cells.foreach_get("locked", snap.locked)
        snap.scale = float(s.display_scale)
        snap.digits = s.digits
        snap.limit = s.limit
        snap.bad_filter = s.bad_filter
        snap.dim_zero = s.dim_zero
        return snap

    def row_visible(self, r: int) -> bool:
        """行が「不正ウェイト」絞り込みの条件に合うか。

        Args:
            r: 行番号（スナップショット内）。

        Returns:
            表示対象なら True。
        """
        mode = self.bad_filter
        if mode == "ALL":
            return True
        total = round(self.totals[r], 6)
        under, over, limit = total < 1.0, total > 1.0, self.counts[r] > self.limit
        return {"UNDER": under, "OVER": over, "LIMIT": limit, "BAD": under or over or limit}[mode]


class WeightModel(QtCore.QAbstractTableModel):
    """頂点（行）× インフルエンス（列）のウェイト表。表示中の行・列だけを持つ。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.snap = Snapshot()
        self.rows: list[int] = []  # 表示行 → スナップショットの行
        self.cols: list[int] = []  # 表示列 → スナップショットの列
        self.generation = -1

    def reload(self, snap: Snapshot, generation: int) -> None:
        """スナップショットを差し替えてモデルをリセットする。

        Args:
            snap: 新しいスナップショット。
            generation: ``table.generation`` の値（変化の検知用）。
        """
        self.beginResetModel()
        self.snap = snap
        self.rows = [r for r in range(len(snap.verts)) if snap.row_visible(r)]
        self.cols = [c for c, v in enumerate(snap.col_visible) if v]
        self.generation = generation
        self.endResetModel()

    def cell_index(self, row: int, col: int) -> int:
        """表示位置から、セル配列（行優先）の添字を返す。

        Args:
            row: 表示行。
            col: 表示列。

        Returns:
            ``values`` / ``locked`` の添字。
        """
        return self.rows[row] * len(self.snap.col_names) + self.cols[col]

    def source_cell(self, row: int, col: int) -> tuple[int, int]:
        """表示位置から ``(テーブル行, テーブル列)`` を返す。

        Args:
            row: 表示行。
            col: 表示列。

        Returns:
            ``WindowManager.siwe`` 上の行・列番号。
        """
        return self.rows[row], self.cols[col]

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        """表示行数。"""
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        """表示列数。"""
        return 0 if parent.isValid() else len(self.cols)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """列見出し（ボーン名）と行見出し（頂点番号）を返す。"""
        snap = self.snap
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return snap.col_names[self.cols[section]].split("|")[-1]
            if role == Qt.ItemDataRole.BackgroundRole:
                return QtGui.QColor(*JOINT_COLORS[self.cols[section] % len(JOINT_COLORS)])
            return None
        r = self.rows[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(snap.verts[r])
        if role == Qt.ItemDataRole.BackgroundRole:
            total = round(snap.totals[r], 6)
            if total < 1.0:
                return QtGui.QColor(*UNDER_WEIGHT)
            if total > 1.0:
                return QtGui.QColor(*OVER_WEIGHT)
            if snap.counts[r] > snap.limit > 0:
                return QtGui.QColor(*OVER_INFLUENCE)
            return QtGui.QColor(*V_HEADER_BG)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignRight
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """セルの表示値・文字色・背景色を返す。"""
        if not index.isValid():
            return None
        snap = self.snap
        i = self.cell_index(index.row(), index.column())
        value = snap.values[i]
        locked = snap.locked[i]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{value * snap.scale:.{snap.digits}f}"
        if role == Qt.ItemDataRole.BackgroundRole:
            return QtGui.QColor(*LOCK_BG) if locked else None
        if role == Qt.ItemDataRole.ForegroundRole:
            if locked:
                return QtGui.QColor(*LOCK_TEXT)
            color = [210, 210, 210]
            r = self.rows[index.row()]
            total = round(snap.totals[r], 6)
            if total < 1.0:
                color = list(UNDER_WEIGHT)
            elif total > 1.0:
                color = list(OVER_WEIGHT)
            elif snap.counts[r] > snap.limit > 0:
                color = list(OVER_INFLUENCE)
            if snap.dim_zero and value <= EPS:
                color = [max(c - ZERO_DARKEN, 43) for c in color]
            return QtGui.QColor(*color)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index):
        """セルは選択可能（編集は入力欄から行う）。"""
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled


class VerticalHeader(QtWidgets.QHeaderView):
    """ボーン名を 90 度回転して描く横方向のヘッダー（縦長の領域に収めて列を狭くする）。"""

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._font = QtGui.QFont("Helvetica", 9)
        self._active_font = QtGui.QFont("Helvetica", 9)
        self._active_font.setWeight(QtGui.QFont.Weight.DemiBold)
        self._metrics = QtGui.QFontMetrics(self._font)
        self._margin = 5
        self.setSectionsClickable(True)
        self.setHighlightSections(True)

    def paintSection(self, painter, rect, index) -> None:
        """セルの背景を塗り、ボーン名を 90 度回転して描く。"""
        model = self.model()
        if model is None:
            return
        name = model.headerData(index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or ""
        color = model.headerData(index, Qt.Orientation.Horizontal, Qt.ItemDataRole.BackgroundRole)
        selection = self.selectionModel()
        active = selection is not None and selection.columnIntersectsSelection(index)
        painter.save()
        painter.fillRect(rect, color)
        painter.setPen(QtGui.QPen(color.darker(130)))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setFont(self._active_font if active else self._font)
        painter.setPen(QtGui.QColor(230, 230, 230))
        painter.translate(rect.left(), rect.bottom())
        painter.rotate(-90)
        text_rect = QtCore.QRect(self._margin, 0, rect.height() - 2 * self._margin, rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        painter.restore()

    def sizeHint(self) -> QtCore.QSize:
        """一番長いボーン名に合わせた高さを返す。"""
        model = self.model()
        if model is None or model.columnCount() == 0:
            return QtCore.QSize(0, 40)
        widest = max(
            self._metrics.horizontalAdvance(str(model.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)))
            for i in range(model.columnCount())
        )
        return QtCore.QSize(0, int(widest * 1.1) + 2 * self._margin)
