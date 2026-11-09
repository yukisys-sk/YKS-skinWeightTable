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


FIRST_COL_UNITS = 5.0  # 頂点番号・オブジェクト名の列の幅
CELL_UNITS = 2.6  # ウェイトセルの幅（"0.500" がちょうど入る程度）
HEADER_CHARS = 10  # 縦積みの見出しに出す最大文字数


def _cell(row, units: float):
    """幅を固定したセル用のサブレイアウトを返す。

    Args:
        row: 親の行レイアウト。
        units: 幅（Blender の UI 単位）。

    Returns:
        幅を ``units`` に固定した行レイアウト。
    """
    sub = row.row(align=True)
    sub.ui_units_x = units
    return sub


def _vertical_header(layout, name: str) -> None:
    """ボーン名を 1 文字ずつ縦に積んだテキストの列見出しを描く（ボタンにはしない）。

    長い名前は、区別しやすい末尾を残して先頭を省略する。

    Args:
        layout: 描画先のレイアウト。
        name: ボーン名。
    """
    shown = name if len(name) <= HEADER_CHARS else "…" + name[-(HEADER_CHARS - 1):]
    col = layout.column(align=True)
    col.scale_y = 0.6
    for ch in shown:
        col.label(text=ch)


class _MainDraw:
    """メインパネル: ウェイトテーブルと入力。"""

    LABEL = "Skin Weight Table"

    def draw(self, context):
        """上段の操作列・テーブル・入力欄を描く。"""
        s = table.settings(context)
        layout = self.layout
        layout.scale_y = 0.85  # UI 全体を少し詰める
        bar = layout.row(align=True)
        bar.prop(s, "lock_ui", text="", icon="LOCKED" if s.lock_ui else "UNLOCKED")
        _op(bar, "siwe.refresh", "", "FILE_REFRESH")
        _op(bar, "siwe.clear_table", "", "X")
        _op(bar, "siwe.select_from_cells", "", "RESTRICT_SELECT_OFF")
        _op(bar, "siwe.open_window", "", "WINDOW")
        _op(bar, "siwe.open_qt_window", "Qt")
        bar.separator()
        bar.prop(s, "display_scale", expand=True)
        bar.prop(s, "auto_update", text="", icon="TIME")
        bar = layout.row(align=True)
        _op(bar, "siwe.show_cells", "Show").all = False
        _op(bar, "siwe.show_cells", "Show All").all = True
        bar.prop(s, "filter_zero", toggle=True)
        _op(bar, "siwe.select_bones", "Joint Hilite")

        # オプションは折りたたまず、表の上にまとめて並べる
        opts = layout.column(align=True)
        opts.scale_y = 0.85
        for draw_section in SECTIONS:
            draw_section(opts, s)
            opts.separator(factor=0.3)

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
        # grid_flow は行数が増えると高さの計算がずれ、下のボタンに重なることがあるため、
        # 行ごとに row を積み上げて描く
        # 表全体の幅を列数から決めて固定する（余白を各セルに配られて列が広がるのを防ぐ）
        wrapper = layout.row()
        wrapper.alignment = "LEFT"
        grid = wrapper.column(align=True)
        grid.ui_units_x = FIRST_COL_UNITS + CELL_UNITS * (len(vcols) + 1)
        # 1 行目: ボーン名を縦に積んだテキスト、2 行目: 列選択ボタン、3 行目: オブジェクト名、以降: 頂点番号 + ウェイト
        head = grid.row(align=True)
        _cell(head, FIRST_COL_UNITS).label(text="")
        for c in vcols:
            _vertical_header(_cell(head, CELL_UNITS), s.cols[c].name)
        _cell(head, CELL_UNITS).label(text="Σ")
        # 見出しテキストの下に、列を一括選択するボタンを置く（マウスを置くとボーン名の全文が出る）
        pick = grid.row(align=True)
        _cell(pick, FIRST_COL_UNITS).label(text="")
        for c in vcols:
            _op(_cell(pick, CELL_UNITS), "siwe.select_cells", "", "TRIA_DOWN", mode="COL", index=c)
        _cell(pick, CELL_UNITS).label(text="")
        name_row = grid.row(align=True)
        _cell(name_row, FIRST_COL_UNITS).label(text=obj.name)
        for _ in vcols:
            _cell(name_row, CELL_UNITS).label(text="")
        _cell(name_row, CELL_UNITS).label(text="")
        scale = float(s.display_scale)
        fmt = f"{{:.{s.digits}f}}"
        for r in vrows:
            row = s.rows[r]
            line = grid.row(align=True)
            _op(_cell(line, FIRST_COL_UNITS), "siwe.select_cells", str(row.vert), mode="ROW", index=r)
            for c in vcols:
                cell = s.cells[r * nc + c]
                sub = _cell(line, CELL_UNITS)
                sub.active = cell.value > 0.0 or not s.dim_zero
                sub.prop(cell, "selected", text=fmt.format(cell.value * scale), toggle=True,
                         icon="LOCKED" if cell.locked else "NONE")
            tot = _cell(line, CELL_UNITS)
            tot.alert = round(row.total, 6) != 1.0
            tot.label(text=fmt.format(row.total * scale))
        layout.separator()
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


def _draw_display(layout, s) -> None:
    """検索・不正ウェイト絞り込み・桁数/丸め/制限を 3 行で描く。

    Args:
        layout: 描画先のレイアウト。
        s: UI 設定。
    """
    row = layout.row(align=True)
    row.prop(s, "search", text="", icon="VIEWZOOM")
    row.prop(s, "search_mode", text="")
    row = layout.row(align=True)
    row.prop(s, "show_all_influences", text="AllGrp", toggle=True)
    row.prop(s, "dim_zero", text="Dim", toggle=True)
    row.prop(s, "bad_filter", text="")
    _op(row, "siwe.select_bad_rows", "", "RESTRICT_SELECT_OFF")
    row = layout.row(align=True)
    row.prop(s, "limit", text="Lim")
    _op(row, "siwe.enforce_limit", "Enf")
    row.prop(s, "digits", text="Dig")
    _op(row, "siwe.round_off", "Round")
    row = layout.row(align=True)
    row.prop(s, "max_rows", text="Rows")
    row.prop(s, "max_cols", text="Cols")


def _draw_smooth(layout, s) -> None:
    """スムース設定と実行ボタンを 1 行で描く。

    Args:
        layout: 描画先のレイアウト。
        s: UI 設定。
    """
    row = layout.row(align=True)
    row.prop(s, "smooth_keep_zero", text="0keep", toggle=True)
    row.prop(s, "smooth_amount", text="Rt")
    row.prop(s, "smooth_iterations", text="It")
    _op(row, "siwe.smooth", "Smooth", hammer=False)
    _op(row, "siwe.smooth", "Hammer", hammer=True)


def _pair(layout, caption: str, copy_op: str, paste_op: str, copy_props=None, paste_props=None) -> None:
    """キャプション付きのコピー/ペースト アイコンボタンを同じ行に並べる。

    Args:
        layout: 描画先のレイアウト。
        caption: 左に出す短い名前。
        copy_op: コピー側のオペレーター ID。
        paste_op: ペースト側のオペレーター ID。
        copy_props: コピー側のオペレータープロパティ。
        paste_props: ペースト側のオペレータープロパティ。
    """
    row = layout.row(align=True)
    row.label(text=caption)
    _op(row, copy_op, "", "COPYDOWN", **(copy_props or {}))
    _op(row, paste_op, "", "PASTEDOWN", **(paste_props or {}))


def _draw_copy(layout, s) -> None:
    """コピー&ペースト系ツールを、2 列に詰めて描く。

    Args:
        layout: 描画先のレイアウト。
        s: UI 設定。
    """
    grid = layout.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=False, align=True)
    _pair(grid, "Cell", "siwe.cell_copy", "siwe.cell_paste")
    _pair(grid, "Vtx", "siwe.vertex_copy", "siwe.vertex_paste")
    _pair(grid, "Move", "siwe.move_influence", "siwe.move_influence", {"step": "COPY"}, {"step": "PASTE"})
    _pair(grid, "Xfer", "siwe.transfer_copy", "siwe.transfer_paste")
    row = layout.row(align=True)
    _op(row, "siwe.simple_copy", "SimpleCopy")
    _op(row, "siwe.simple_paste", "Idx", method="INDEX")
    _op(row, "siwe.simple_paste", "Pos", method="POSITION")


def _draw_symmetry(layout, s) -> None:
    """左右対称ツールと命名規則を 3 行で描く。

    Args:
        layout: 描画先のレイアウト。
        s: UI 設定。
    """
    row = layout.row(align=True)
    row.prop(s, "mirror_axis", expand=True)
    row.prop(s, "mirror_direction", text="")
    row.prop(s, "mirror_threshold", text="")
    row = layout.row(align=True)
    _op(row, "siwe.symmetrize", "Sym")
    _op(row, "siwe.auto_symmetry", "Auto")
    _op(row, "siwe.merge_skinned", "Merge")
    layout.prop(s, "mirror_rules", text="")


def _draw_misc(layout, s) -> None:
    """スキン状態・Freeze・Go Export/Import・インフルエンス管理を 3 行で描く。

    Args:
        layout: 描画先のレイアウト。
        s: UI 設定。
    """
    row = layout.row(align=True)
    _op(row, "siwe.freeze", "Frz", keep_skin=False)
    _op(row, "siwe.freeze", "Frz_M", keep_skin=True)
    _op(row, "siwe.toggle_mute", "Mute")
    _op(row, "siwe.bind_pose", "Bind")
    _op(row, "siwe.go_export", "Exp")
    _op(row, "siwe.go_import", "Imp")
    row = layout.row(align=True)
    row.prop(s, "new_influence", text="")
    _op(row, "siwe.add_influence", "", "ADD")
    _op(row, "siwe.remove_influence", "", "REMOVE")
    _op(row, "siwe.remove_unused", "", "TRASH")


SECTIONS = (_draw_display, _draw_smooth, _draw_copy, _draw_symmetry, _draw_misc)


MIXINS = (("main", _MainDraw),)


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
