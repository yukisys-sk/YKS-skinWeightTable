"""3D ビューポートのサイドバー（N パネル）に表示する UI。"""

from __future__ import annotations

import bpy

from . import table
from .ops_table import row_is_bad


def _op(layout, idname: str, text: str, icon: str = "NONE", **props):
    """オペレーターボタンを置き、プロパティを設定して返す。

    Args:
        layout: 配置先レイアウト。
        idname: オペレーター ID。
        text: ボタン文字列。
        icon: アイコン名。
        **props: オペレータープロパティ。

    Returns:
        オペレーターのプロパティ。
    """
    op = layout.operator(idname, text=text, icon=icon)
    for k, v in props.items():
        setattr(op, k, v)
    return op


class _MainDraw:
    """メインパネル: ウェイトテーブルと入力。"""

    LABEL = "Skin Weight Table"

    def draw(self, context):
        """上段の操作列・テーブル・入力欄を描く。"""
        s = table.settings(context)
        layout = self.layout
        bar = layout.row(align=True)
        bar.prop(s, "lock_ui", text="", icon="LOCKED" if s.lock_ui else "UNLOCKED")
        _op(bar, "siwe.refresh", "", "FILE_REFRESH")
        _op(bar, "siwe.clear_table", "", "X")
        _op(bar, "siwe.select_from_cells", "", "RESTRICT_SELECT_OFF")
        _op(bar, "siwe.open_window", "", "WINDOW")
        bar.separator()
        bar.prop(s, "display_scale", expand=True)
        bar.prop(s, "auto_update", text="", icon="TIME")
        bar = layout.row(align=True)
        _op(bar, "siwe.show_cells", "Show").all = False
        _op(bar, "siwe.show_cells", "Show All").all = True
        bar.prop(s, "filter_zero", toggle=True)
        _op(bar, "siwe.select_bones", "Joint Hilite")

        self.draw_table(layout, s)
        self.draw_input(layout, s)

    def draw_table(self, layout, s):
        """ウェイトテーブルを描く（ページ送り付き）。"""
        obj = table.active_mesh(bpy.context)
        if obj is None:
            layout.label(text="メッシュを選択してください", icon="INFO")
            return
        nc = len(s.cols)
        rows = [i for i, r in enumerate(s.rows) if row_is_bad(s, r)]
        cols = [i for i, c in enumerate(s.cols) if c.visible]
        if not rows or not cols:
            layout.label(text="頂点を選択してください" if not rows else "表示できるインフルエンスがありません", icon="INFO")
            return
        vrows = rows[s.row_offset: s.row_offset + s.max_rows]
        vcols = cols[s.col_offset: s.col_offset + s.max_cols]
        nav = layout.row(align=True)
        _op(nav, "siwe.page", "", "TRIA_LEFT", axis="COL", step=-1)
        nav.label(text=f"{len(rows)} verts / {len(cols)} infs   col {s.col_offset + 1}")
        _op(nav, "siwe.page", "", "TRIA_RIGHT", axis="COL", step=1)
        _op(nav, "siwe.page", "", "TRIA_UP", axis="ROW", step=-1)
        _op(nav, "siwe.page", "", "TRIA_DOWN", axis="ROW", step=1)
        grid = layout.grid_flow(row_major=True, columns=len(vcols) + 2, even_columns=False, even_rows=True, align=True)
        _op(grid, "siwe.select_cells", "All", mode="ALL")
        for c in vcols:
            col = s.cols[c]
            _op(grid, "siwe.select_cells", col.name[-8:], mode="COL", index=c)
        grid.label(text="Σ")
        scale = float(s.display_scale)
        fmt = f"{{:.{s.digits}f}}"
        for r in vrows:
            row = s.rows[r]
            _op(grid, "siwe.select_cells", str(row.vert), mode="ROW", index=r)
            for c in vcols:
                cell = s.cells[r * nc + c]
                sub = grid.row(align=True)
                sub.active = cell.value > 0.0 or not s.dim_zero
                sub.prop(cell, "selected", text=fmt.format(cell.value * scale), toggle=True,
                         icon="LOCKED" if cell.locked else "NONE")
            tot = grid.row(align=True)
            tot.alert = round(row.total, 6) != 1.0
            tot.label(text=fmt.format(row.total * scale))
        sel = layout.row(align=True)
        for text, mode in (("All", "ALL"), ("None", "NONE"), ("Invert", "INVERT")):
            _op(sel, "siwe.select_cells", text, mode=mode)

    def draw_input(self, layout, s):
        """入力モード・値・正規化・固定値ボタンを描く。"""
        box = layout.box()
        box.row().prop(s, "input_mode", expand=True)
        row = box.row(align=True)
        row.prop(s, "value", text="")
        _op(row, "siwe.apply_input", "Apply", "CHECKMARK")
        box.prop(s, "value", slider=True, text="Slider")
        flags = box.row(align=True)
        flags.prop(s, "normalize", toggle=True)
        flags.prop(s, "unlimited", toggle=True)
        fixed = box.row(align=True)
        for v in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            _op(fixed, "siwe.set_fixed", f"{v:g}", value=v)
        lock = box.row(align=True)
        _op(lock, "siwe.lock", "Lock Wt", "LOCKED", mode="LOCK")
        _op(lock, "siwe.lock", "Unlock Wt", "UNLOCKED", mode="UNLOCK")
        _op(lock, "siwe.lock", "Clear Locks", "X", mode="CLEAR")


class _DisplayDraw:
    """表示・検証オプション。"""

    LABEL = "Display / Check"
    CLOSED = True

    def draw(self, context):
        """検索・不正ウェイト絞り込み・桁数/丸め/制限を描く。"""
        s = table.settings(context)
        col = self.layout.column()
        col.prop(s, "search", icon="VIEWZOOM")
        col.prop(s, "search_mode", expand=True)
        col.prop(s, "show_all_influences")
        col.prop(s, "dim_zero")
        col.prop(s, "max_rows")
        col.prop(s, "max_cols")
        col.separator()
        col.prop(s, "bad_filter")
        _op(col, "siwe.select_bad_rows", "Select Bad Vertices")
        col.separator()
        col.prop(s, "limit")
        _op(col, "siwe.enforce_limit", "Enforce Limit")
        col.prop(s, "digits")
        _op(col, "siwe.round_off", "Round Off")


class _SmoothDraw:
    """スムース/ハンマー。"""

    LABEL = "Smooth / Hammer"
    CLOSED = True

    def draw(self, context):
        """スムース設定と実行ボタンを描く。"""
        s = table.settings(context)
        col = self.layout.column()
        col.prop(s, "smooth_keep_zero")
        col.prop(s, "smooth_amount")
        col.prop(s, "smooth_iterations")
        row = col.row(align=True)
        _op(row, "siwe.smooth", "Smooth", hammer=False)
        _op(row, "siwe.smooth", "Hammer", hammer=True)


class _CopyDraw:
    """コピー&ペースト系ツール。"""

    LABEL = "Copy / Paste / Transfer"
    CLOSED = True

    def draw(self, context):
        """各コピペ系ボタンを描く。"""
        col = self.layout.column(align=True)
        col.label(text="Cell (Excel like)")
        row = col.row(align=True)
        _op(row, "siwe.cell_copy", "Copy", "COPYDOWN")
        _op(row, "siwe.cell_paste", "Paste", "PASTEDOWN")
        col.label(text="Vertex")
        row = col.row(align=True)
        _op(row, "siwe.vertex_copy", "Copy", "COPYDOWN")
        _op(row, "siwe.vertex_paste", "Paste", "PASTEDOWN")
        col.label(text="Move Influence Weight")
        row = col.row(align=True)
        _op(row, "siwe.move_influence", "Copy From", "COPYDOWN", step="COPY")
        _op(row, "siwe.move_influence", "Move To", "PASTEDOWN", step="PASTE")
        col.label(text="Simple Weight")
        _op(col, "siwe.simple_copy", "Simple Weight Copy", "COPYDOWN")
        _op(col, "siwe.simple_paste", "Paste (Name Index)", "PASTEDOWN", method="INDEX")
        _op(col, "siwe.simple_paste", "Paste (Name Position)", "PASTEDOWN", method="POSITION")
        col.label(text="Transfer Weight")
        row = col.row(align=True)
        _op(row, "siwe.transfer_copy", "Copy", "COPYDOWN")
        _op(row, "siwe.transfer_paste", "Paste", "PASTEDOWN")


class _SymmetryDraw:
    """左右対称ツールと命名規則。"""

    LABEL = "Symmetry"
    CLOSED = True

    def draw(self, context):
        """対称ツールの設定とボタンを描く。"""
        s = table.settings(context)
        col = self.layout.column()
        col.prop(s, "mirror_axis", expand=True)
        col.prop(s, "mirror_direction", expand=True)
        col.prop(s, "mirror_threshold")
        _op(col, "siwe.symmetrize", "Weight Symmetrize")
        _op(col, "siwe.auto_symmetry", "Auto Symmetry")
        _op(col, "siwe.merge_skinned", "Merge With Skinning")
        col.label(text="Naming Rules（左,右 / 1行1組）")
        col.prop(s, "mirror_rules", text="")


class _MiscDraw:
    """スキン状態・Freeze・Go Export/Import・インフルエンス管理。"""

    LABEL = "Skin / Influences / Misc"
    CLOSED = True

    def draw(self, context):
        """各種ボタンを描く。"""
        s = table.settings(context)
        col = self.layout.column(align=True)
        row = col.row(align=True)
        _op(row, "siwe.freeze", "Freeze", keep_skin=False)
        _op(row, "siwe.freeze", "Freeze_M", keep_skin=True)
        row = col.row(align=True)
        _op(row, "siwe.toggle_mute", "Toggle Mute Skinning")
        _op(row, "siwe.bind_pose", "Go to Bind Pose")
        row = col.row(align=True)
        _op(row, "siwe.go_export", "Go Export")
        _op(row, "siwe.go_import", "Go Import")
        col.separator()
        col.prop(s, "new_influence", text="")
        row = col.row(align=True)
        _op(row, "siwe.add_influence", "Add Influence", "ADD")
        _op(row, "siwe.remove_influence", "Remove Influence", "REMOVE")
        _op(col, "siwe.remove_unused", "Remove Unused Influences")



MIXINS = (
    ("main", _MainDraw),
    ("display", _DisplayDraw),
    ("smooth", _SmoothDraw),
    ("copy", _CopyDraw),
    ("symmetry", _SymmetryDraw),
    ("misc", _MiscDraw),
)


def _make_panels(prefix: str, space: str, region: str, **extra) -> list[type]:
    """描画ミキシンから、指定したエディタ用のパネルクラス一式を作る。

    Args:
        prefix: ``bl_idname`` の接頭辞（例: ``SIWE_PT``）。親子関係もこの接頭辞で結ぶ。
        space: ``bl_space_type``。
        region: ``bl_region_type``。
        **extra: 全パネルに加える属性（``bl_context`` など）。

    Returns:
        登録するパネルクラスのリスト（メインが先頭）。
    """
    classes = []
    for key, mixin in MIXINS:
        attrs = {
            "bl_idname": f"{prefix}_{key}",
            "bl_label": mixin.LABEL,
            "bl_space_type": space,
            "bl_region_type": region,
            **extra,
        }
        if key == "main":
            if space == "VIEW_3D":
                attrs["bl_category"] = "Skin Weight"
        else:
            attrs["bl_parent_id"] = f"{prefix}_main"
            attrs["bl_options"] = {"DEFAULT_CLOSED"}
        classes.append(type(f"{prefix}_{key}", (mixin, bpy.types.Panel), attrs))
    return classes


def _window_poll(cls, context: bpy.types.Context) -> bool:
    """別ウィンドウ版は、アクティブオブジェクトがメッシュのときだけ表示する。"""
    return table.active_mesh(context) is not None


SIDEBAR_CLASSES = _make_panels("SIWE_PT", "VIEW_3D", "UI")
WINDOW_CLASSES = _make_panels("SIWE_PT_win", "PROPERTIES", "WINDOW", bl_context="data")
WINDOW_CLASSES[0].poll = classmethod(_window_poll)
CLASSES = tuple(SIDEBAR_CLASSES + WINDOW_CLASSES)


class SIWE_OT_open_window(bpy.types.Operator):
    """Skin Weight Table を別ウィンドウ（プロパティエディタ）で開く。"""

    bl_idname = "siwe.open_window"
    bl_label = "Open in New Window"
    bl_description = "Skin Weight Table を別ウィンドウで開く（Object Data タブに表示される）"

    @classmethod
    def poll(cls, context):
        """ウィンドウがあり、アクティブがメッシュのときだけ実行可能（バックグラウンド実行では不可）。"""
        return not bpy.app.background and context.window is not None and table.active_mesh(context) is not None

    def execute(self, context):
        """現在のエリアを複製した新ウィンドウを作り、プロパティエディタの Object Data タブにする。"""
        wm = context.window_manager
        area = context.area or next((a for a in context.screen.areas if a.type == "VIEW_3D"), None)
        if area is None:
            self.report({"ERROR"}, "ウィンドウを作る元のエリアが見つかりません。3D ビューから実行してください")
            return {"CANCELLED"}
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        before = set(wm.windows)
        with context.temp_override(area=area, region=region):
            bpy.ops.wm.window_new()
        created = [w for w in wm.windows if w not in before]
        if not created:
            self.report({"ERROR"}, "新しいウィンドウを作れませんでした")
            return {"CANCELLED"}
        win = created[0]
        win.screen.areas[0].type = "PROPERTIES"
        # エディタを切り替えた直後は context の候補が空のため、描画が済むまで少し待って設定する
        attempts = [0]

        def set_context() -> float | None:
            """Object Data タブを選ぶ。候補が出るまで 0.1 秒ごとに最大 30 回試す。"""
            try:
                area = win.screen.areas[0]
                area.spaces.active.context = "DATA"
                area.tag_redraw()
                return None
            except (TypeError, ReferenceError):
                attempts[0] += 1
                return 0.1 if attempts[0] < 30 else None

        bpy.app.timers.register(set_context, first_interval=0.1)
        return {"FINISHED"}


def _view_menu(self, context: bpy.types.Context) -> None:
    """3D ビューの View メニューに項目を追加する。"""
    self.layout.separator()
    self.layout.operator(SIWE_OT_open_window.bl_idname, icon="WINDOW")


CLASSES = CLASSES + (SIWE_OT_open_window,)


def register_menu() -> None:
    """View メニューへの項目追加を登録する。"""
    bpy.types.VIEW3D_MT_view.append(_view_menu)


def unregister_menu() -> None:
    """View メニューへの項目追加を解除する。"""
    bpy.types.VIEW3D_MT_view.remove(_view_menu)
