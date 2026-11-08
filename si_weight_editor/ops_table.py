"""テーブル操作（選択・入力・ロック・丸め・コピー/ペースト・インフルエンス移動）のオペレーター。"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, IntProperty

from . import mesh_io, table
from .core import weight_math as wm

# セル/頂点/インフルエンス移動のクリップボード（セッション内のみ）
_clip: dict[str, object] = {"cells": [], "verts": [], "move_sources": []}


class SIWE_OT_base(bpy.types.Operator):
    """テーブル系オペレーターの基底（メッシュ必須・Undo 対応）。"""

    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        """アクティブオブジェクトがメッシュのときだけ実行可能。"""
        return table.active_mesh(context) is not None

    def fail(self, exc: Exception) -> set[str]:
        """例外を原因付きでレポートして終了する。

        Args:
            exc: 発生した例外。

        Returns:
            ``{'CANCELLED'}``。
        """
        self.report({"ERROR"}, f"{self.bl_label} に失敗しました: {exc}")
        return {"CANCELLED"}


class SIWE_OT_refresh(SIWE_OT_base):
    """現在の選択をテーブルに反映する。"""

    bl_idname = "siwe.refresh"
    bl_label = "Refresh"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        """テーブルを再構築する。"""
        table.refresh(context)
        return {"FINISHED"}


class SIWE_OT_clear_table(bpy.types.Operator):
    """テーブル表示をクリアする。"""

    bl_idname = "siwe.clear_table"
    bl_label = "Clear"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        """テーブルを空にする。"""
        table.clear(table.settings(context))
        return {"FINISHED"}


class SIWE_OT_select_cells(bpy.types.Operator):
    """セル選択の一括操作（行・列・全選択・解除・反転）。"""

    bl_idname = "siwe.select_cells"
    bl_label = "Select Cells"
    bl_options = {"INTERNAL"}

    mode: bpy.props.EnumProperty(
        items=[(m, m.title(), "") for m in ("ALL", "NONE", "INVERT", "ROW", "COL")], default="ALL"
    )
    index: IntProperty(default=0)
    extend: BoolProperty(default=False, options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        """列見出しでは、ボーン名の全文をツールチップに出す。"""
        s = table.settings(context)
        if properties.mode == "COL" and 0 <= properties.index < len(s.cols):
            return f"{s.cols[properties.index].name}（列を選択。Shift で追加）"
        return "セルの選択を切り替える（Shift で追加）"

    def invoke(self, context, event):
        """Shift 押下で追加選択にする。"""
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        """指定範囲のセル選択を切り替える。"""
        s = table.settings(context)
        nc = len(s.cols)
        if not nc:
            return {"CANCELLED"}
        cells = s.cells
        idx = range(len(cells))
        if self.mode == "ROW":
            target = [i for i in idx if i // nc == self.index]
        elif self.mode == "COL":
            target = [i for i in idx if i % nc == self.index]
        else:
            target = list(idx)
        if self.mode in ("ALL", "NONE", "INVERT"):
            for i in target:
                cells[i].selected = {"ALL": True, "NONE": False, "INVERT": not cells[i].selected}[self.mode]
            return {"FINISHED"}
        state = not all(cells[i].selected for i in target)
        if not self.extend:
            for cell in cells:
                cell.selected = False
        for i in target:
            cells[i].selected = state
        if self.mode == "COL":
            for k, col in enumerate(s.cols):
                col.selected = state and k == self.index
        return {"FINISHED"}


class SIWE_OT_page(bpy.types.Operator):
    """表示範囲（行/列）をずらす。"""

    bl_idname = "siwe.page"
    bl_label = "Page"
    bl_options = {"INTERNAL"}

    axis: bpy.props.EnumProperty(items=[("ROW", "Row", ""), ("COL", "Column", "")], default="ROW")
    step: IntProperty(default=1)

    def execute(self, context):
        """オフセットを増減する（範囲外は丸める）。"""
        s = table.settings(context)
        if self.axis == "ROW":
            limit = max(len(s.rows) - 1, 0)
            s.row_offset = max(0, min(s.row_offset + self.step * s.max_rows, limit))
        else:
            vis = sum(1 for c in s.cols if c.visible)
            s.col_offset = max(0, min(s.col_offset + self.step * s.max_cols, max(vis - 1, 0)))
        return {"FINISHED"}


class SIWE_OT_apply_input(SIWE_OT_base):
    """入力値を選択セルへ適用する。"""

    bl_idname = "siwe.apply_input"
    bl_label = "Apply"

    def execute(self, context):
        """Abs/Add/Add% と正規化・ロックを考慮して書き込む。"""
        try:
            n = table.apply_input(context)
        except (RuntimeError, KeyError, ValueError) as exc:
            return self.fail(exc)
        self.report({"INFO"}, f"{n} 頂点を更新しました")
        return {"FINISHED"}


class SIWE_OT_set_fixed(SIWE_OT_base):
    """固定値ボタン: 入力欄へ値を入れて即適用する。"""

    bl_idname = "siwe.set_fixed"
    bl_label = "Fixed Value"

    value: bpy.props.FloatProperty(default=0.0)

    def execute(self, context):
        """値を入力欄に設定して適用する。"""
        s = table.settings(context)
        s.value = self.value * float(s.display_scale)
        try:
            n = table.apply_input(context)
        except (RuntimeError, KeyError, ValueError) as exc:
            return self.fail(exc)
        self.report({"INFO"}, f"{n} 頂点を更新しました")
        return {"FINISHED"}


class SIWE_OT_lock(SIWE_OT_base):
    """選択セルのロック/アンロック/全解除。"""

    bl_idname = "siwe.lock"
    bl_label = "Lock Weight"

    mode: bpy.props.EnumProperty(items=[("LOCK", "Lock", ""), ("UNLOCK", "Unlock", ""), ("CLEAR", "Clear", "")], default="LOCK")

    def execute(self, context):
        """ロック情報をオブジェクトへ保存してテーブルを更新する。"""
        s = table.settings(context)
        obj = table.active_mesh(context)
        try:
            if self.mode == "CLEAR":
                for o in {o for o in context.selected_objects if o.type == "MESH"} | {obj}:
                    table.save_locks(o, {})
            else:
                locks = table.load_locks(obj)
                for r, c in table.selected_cells(s):
                    v, name = s.rows[r].vert, s.cols[c].name
                    bucket = locks.setdefault(v, set())
                    (bucket.add if self.mode == "LOCK" else bucket.discard)(name)
                table.save_locks(obj, locks)
        except ValueError as exc:
            return self.fail(exc)
        table.refresh(context)
        return {"FINISHED"}


class SIWE_OT_select_from_cells(SIWE_OT_base):
    """セル上で選択した頂点だけを実際に選択する（⇄）。"""

    bl_idname = "siwe.select_from_cells"
    bl_label = "Select Vertices From Cells"

    def execute(self, context):
        """選択セルを持つ行の頂点を選択し、テーブルを絞り込む。"""
        s = table.settings(context)
        rows = {r for r, _ in table.selected_cells(s)}
        if not rows:
            self.report({"WARNING"}, "セルが選択されていません")
            return {"CANCELLED"}
        mesh_io.set_selected_vertices(table.active_mesh(context), {s.rows[r].vert for r in rows})
        table.refresh(context)
        return {"FINISHED"}


class SIWE_OT_show_cells(SIWE_OT_base):
    """Show: 選択セルの頂点とインフルエンスだけに表示を絞る / Show All: 全表示。"""

    bl_idname = "siwe.show_cells"
    bl_label = "Show"

    all: BoolProperty(default=False)

    def execute(self, context):
        """表示を絞り込む、または全インフルエンスを表示する。"""
        s = table.settings(context)
        if self.all:
            s.filter_zero = False
            for col in s.cols:
                col.visible = True
            return {"FINISHED"}
        cells = table.selected_cells(s)
        if not cells:
            self.report({"WARNING"}, "セルが選択されていません")
            return {"CANCELLED"}
        keep = {c for _, c in cells}
        for k, col in enumerate(s.cols):
            col.visible = k in keep
        return {"FINISHED"}


class SIWE_OT_select_bad_rows(SIWE_OT_base):
    """不正ウェイト（合計≠1 / 制限超過）の頂点を選択する。"""

    bl_idname = "siwe.select_bad_rows"
    bl_label = "Select Bad Vertices"

    def execute(self, context):
        """Show 設定に従い、条件に合う頂点だけを選択する。"""
        s = table.settings(context)
        picked = {r.vert for r in s.rows if row_is_bad(s, r)}
        mesh_io.set_selected_vertices(table.active_mesh(context), picked)
        table.refresh(context)
        self.report({"INFO"}, f"{len(picked)} 頂点を選択しました")
        return {"FINISHED"}


def row_is_bad(s, row) -> bool:
    """行が ``bad_filter`` の条件に当てはまるか。

    Args:
        s: UI 設定。
        row: テーブルの行。

    Returns:
        表示対象なら True。
    """
    mode = s.bad_filter
    if mode == "ALL":
        return True
    total = round(row.total, 6)
    under, over, limit = total < 1.0, total > 1.0, row.count > s.limit
    return {"UNDER": under, "OVER": over, "LIMIT": limit, "BAD": under or over or limit}[mode]


class SIWE_OT_round_off(SIWE_OT_base):
    """表示桁数で四捨五入する。"""

    bl_idname = "siwe.round_off"
    bl_label = "Round Off"

    def execute(self, context):
        """テーブル内の全行を Digits 桁に丸める。"""
        s = table.settings(context)
        try:
            n = table.edit_rows(context, lambda r, row, lk, cols: wm.round_weights(row, s.digits), only_selected_rows=False)
        except RuntimeError as exc:
            return self.fail(exc)
        self.report({"INFO"}, f"{n} 頂点を丸めました")
        return {"FINISHED"}


class SIWE_OT_enforce_limit(SIWE_OT_base):
    """インフルエンス数を Enforce Limit 以下にして正規化する。"""

    bl_idname = "siwe.enforce_limit"
    bl_label = "Enforce Limit"

    def execute(self, context):
        """制限を超える頂点だけ、小さい順にインフルエンスを落とす。"""
        s = table.settings(context)

        def fn(r, row, locked, cols):
            """1 行分の制限適用。"""
            if sum(1 for w in row if w > table.EPS) <= s.limit:
                return None
            limited = wm.enforce_influence_limit(row, s.limit, locked)
            keep = [i for i, w in enumerate(limited) if w > 0.0]
            out, _ = wm.normalize_row(limited, row, keep, locked, force=True, enforce=1)
            return out

        try:
            n = table.edit_rows(context, fn, only_selected_rows=False)
        except RuntimeError as exc:
            return self.fail(exc)
        self.report({"INFO"}, f"{n} 頂点にインフルエンス制限を適用しました")
        return {"FINISHED"}


class SIWE_OT_select_bones(SIWE_OT_base):
    """選択列に対応するボーンをアーマチュア上で選択する（Joint Hilite）。"""

    bl_idname = "siwe.select_bones"
    bl_label = "Select Joints"

    def execute(self, context):
        """選択列（無ければ選択セルの列）のボーンを選択状態にする。"""
        s = table.settings(context)
        obj = table.active_mesh(context)
        arm = mesh_io.armature_of(obj)
        if arm is None:
            self.report({"ERROR"}, "Armature モディファイアが無いため、ボーンを特定できません")
            return {"CANCELLED"}
        names = {s.cols[c].name for _, c in table.selected_cells(s)} | {c.name for c in s.cols if c.selected}
        if not names:
            self.report({"WARNING"}, "列またはセルが選択されていません")
            return {"CANCELLED"}
        # Blender 5 では選択状態が PoseBone.select、4.x では Bone.select
        if "select" in bpy.types.PoseBone.bl_rna.properties:
            for pb in arm.pose.bones:
                pb.select = pb.name in names
        else:
            for b in arm.data.bones:
                b.select = b.select_head = b.select_tail = b.name in names
        return {"FINISHED"}


class SIWE_OT_cell_copy(SIWE_OT_base):
    """選択セルの値をコピーする（Excel 風）。"""

    bl_idname = "siwe.cell_copy"
    bl_label = "Cell Copy"

    def execute(self, context):
        """行→列の順で選択セルの値を保持する。"""
        s = table.settings(context)
        nc = len(s.cols)
        cells = table.selected_cells(s)
        if not cells:
            self.report({"WARNING"}, "セルが選択されていません")
            return {"CANCELLED"}
        values = table.cell_flags(s, "value")
        _clip["cells"] = [values[r * nc + c] for r, c in cells]
        self.report({"INFO"}, f"{len(cells)} セルをコピーしました")
        return {"FINISHED"}


class SIWE_OT_cell_paste(SIWE_OT_base):
    """コピーしたセル値を選択セルへペーストする（範囲が大きければ繰り返し）。"""

    bl_idname = "siwe.cell_paste"
    bl_label = "Cell Paste"

    def execute(self, context):
        """選択セルへ順に値を入れ、ロック・正規化設定を考慮する。"""
        s = table.settings(context)
        src = list(_clip["cells"])
        cells = table.selected_cells(s)
        if not cells:
            self.report({"WARNING"}, "ペースト先のセルが選択されていません")
            return {"CANCELLED"}
        try:
            values = wm.tile_values(src, len(cells))
        except ValueError as exc:
            return self.fail(exc)
        assign = dict(zip(cells, values))

        def fn(r, row, locked, cols):
            """1 行分のペースト。"""
            new = list(row)
            for c in cols:
                if c not in locked:
                    new[c] = assign[(r, c)]
            out, bake = wm.normalize_row(new, row, cols, locked, force=s.normalize, unlimited=s.unlimited)
            return out if bake else None

        try:
            table.edit_rows(context, fn)
        except RuntimeError as exc:
            return self.fail(exc)
        return {"FINISHED"}


class SIWE_OT_vertex_copy(SIWE_OT_base):
    """選択頂点のウェイト（全インフルエンス）をコピーする。"""

    bl_idname = "siwe.vertex_copy"
    bl_label = "Vertex Copy"

    def execute(self, context):
        """選択頂点のウェイトを頂点番号順に保持する。"""
        obj = table.active_mesh(context)
        verts = mesh_io.selected_vertices(obj)
        if not verts:
            self.report({"WARNING"}, "頂点が選択されていません")
            return {"CANCELLED"}
        data = mesh_io.read_weights(obj, verts)
        _clip["verts"] = [data[v] for v in verts]
        self.report({"INFO"}, f"{len(verts)} 頂点をコピーしました")
        return {"FINISHED"}


class SIWE_OT_vertex_paste(SIWE_OT_base):
    """コピーした頂点ウェイトを選択頂点へ繰り返しペーストする（無いインフルエンスは自動追加）。"""

    bl_idname = "siwe.vertex_paste"
    bl_label = "Vertex Paste"

    def execute(self, context):
        """ペースト先の全インフルエンスを入れ替える。"""
        obj = table.active_mesh(context)
        verts = mesh_io.selected_vertices(obj)
        src = list(_clip["verts"])
        if not verts:
            self.report({"WARNING"}, "ペースト先の頂点が選択されていません")
            return {"CANCELLED"}
        try:
            rows = wm.tile_values(src, len(verts))
            current = mesh_io.read_weights(obj, verts)
            out = {}
            for v, new in zip(verts, rows):
                merged = {name: 0.0 for name in current[v]}
                merged.update(new)
                out[v] = merged
            mesh_io.write_weights(obj, out, create_groups=True)
        except (ValueError, KeyError) as exc:
            return self.fail(exc)
        table.refresh(context)
        return {"FINISHED"}


class SIWE_OT_move_influence(SIWE_OT_base):
    """Move Influence Weight: 選択列のウェイトを別の選択列へ移す。"""

    bl_idname = "siwe.move_influence"
    bl_label = "Move Influence Weight"

    step: bpy.props.EnumProperty(items=[("COPY", "Copy", "移動元の列を記憶"), ("PASTE", "Paste", "記憶した列から選択列へ移動")], default="COPY")

    def execute(self, context):
        """Copy で移動元列（名前）を記憶し、Paste で選択列へ均等分配する。"""
        s = table.settings(context)
        cols = sorted({c for _, c in table.selected_cells(s)} | {k for k, col in enumerate(s.cols) if col.selected})
        if not cols:
            self.report({"WARNING"}, "列またはセルが選択されていません")
            return {"CANCELLED"}
        if self.step == "COPY":
            _clip["move_sources"] = [s.cols[c].name for c in cols]
            self.report({"INFO"}, "移動元: " + ", ".join(_clip["move_sources"]))
            return {"FINISHED"}
        names = [c.name for c in s.cols]
        src = [names.index(n) for n in _clip["move_sources"] if n in names]
        if not src:
            self.report({"ERROR"}, "移動元が未設定か、テーブルに表示されていません。先に Copy してください")
            return {"CANCELLED"}
        # 全行を対象にするため、行ごとに選択列を移動先として渡す
        try:
            table.edit_rows(
                context,
                lambda r, row, locked, _c: wm.move_weights(row, src, cols, locked),
                only_selected_rows=False,
            )
        except RuntimeError as exc:
            return self.fail(exc)
        return {"FINISHED"}


CLASSES = (
    SIWE_OT_refresh,
    SIWE_OT_clear_table,
    SIWE_OT_select_cells,
    SIWE_OT_page,
    SIWE_OT_apply_input,
    SIWE_OT_set_fixed,
    SIWE_OT_lock,
    SIWE_OT_select_from_cells,
    SIWE_OT_show_cells,
    SIWE_OT_select_bad_rows,
    SIWE_OT_round_off,
    SIWE_OT_enforce_limit,
    SIWE_OT_select_bones,
    SIWE_OT_cell_copy,
    SIWE_OT_cell_paste,
    SIWE_OT_vertex_copy,
    SIWE_OT_vertex_paste,
    SIWE_OT_move_influence,
)
