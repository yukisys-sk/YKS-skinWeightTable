"""サブツール群のオペレーター（スムース/ハンマー・Freeze・コピペ・転写・対称・インフルエンス管理など）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import bmesh
import bpy
from bpy.props import BoolProperty
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

from . import mesh_io, table
from .core import mirror_rules
from .core import weight_math as wm
from .ops_table import SIWE_OT_base

WORK_DIR = Path(tempfile.gettempdir()) / "siwe"
_transfer_sources: list[str] = []


def _meshes(context: bpy.types.Context) -> list[bpy.types.Object]:
    """選択中のメッシュオブジェクト（アクティブを先頭）を返す。

    Args:
        context: 現在のコンテキスト。

    Returns:
        メッシュオブジェクトのリスト。
    """
    objs = [o for o in context.selected_objects if o.type == "MESH"]
    act = context.object
    if act is not None and act.type == "MESH":
        objs = [act] + [o for o in objs if o != act]
    return objs


def _objs_for_edit(context: bpy.types.Context) -> list[bpy.types.Object]:
    """マルチオブジェクト編集中のメッシュも含めた対象メッシュを返す。

    Args:
        context: 現在のコンテキスト。

    Returns:
        メッシュオブジェクトのリスト。
    """
    return list(context.objects_in_mode_unique_data) if context.mode == "EDIT_MESH" else _meshes(context)


# --------------------------------------------------------------------------- smooth / hammer
class SIWE_OT_smooth(SIWE_OT_base):
    """選択頂点のウェイトをスムース/ハンマーする。"""

    bl_idname = "siwe.smooth"
    bl_label = "Smooth"

    hammer: BoolProperty(default=False, description="自分自身を含めず隣接頂点の平均にする")
    keep_zero: BoolProperty(default=False, description="元が 0 のインフルエンスは 0 のままにする（設定の Keep Zero とどちらかが有効なら適用）")

    def execute(self, context):
        """隣接頂点との平均で選択頂点のウェイトを更新する（Keep Zero / Ratio / Iterations 対応）。"""
        s = table.settings(context)
        obj = table.active_mesh(context)
        sel = mesh_io.selected_vertices(obj)
        if not sel:
            self.report({"WARNING"}, "頂点が選択されていません")
            return {"CANCELLED"}
        adj = mesh_io.neighbors(obj)
        names = mesh_io.influence_names(obj, not s.show_all_influences)
        used = sorted(set(sel) | {n for v in sel for n in adj[v]})
        pos = {v: i for i, v in enumerate(used)}
        data = mesh_io.read_weights(obj, used)
        rows = [[data[v].get(n, 0.0) for n in names] for v in used]
        nbrs = [[pos[n] for n in adj[v] if n in pos] for v in used]
        result = wm.smooth_rows(
            rows, nbrs, s.smooth_amount, s.smooth_keep_zero or self.keep_zero, s.smooth_iterations,
            targets=[pos[v] for v in sel], include_self=not self.hammer,
        )
        rows_out = {v: result[pos[v]] for v in sel}
        if s.smooth_obey_limit:
            rows_out = {v: wm.limit_row(row, s.limit) for v, row in rows_out.items()}
        mesh_io.write_weights(obj, {v: dict(zip(names, row)) for v, row in rows_out.items()})
        table.refresh(context)
        return {"FINISHED"}


# --------------------------------------------------------------------------- freeze
class SIWE_OT_freeze(bpy.types.Operator):
    """ヒストリ（モディファイア）をベイクする。Freeze はスキニングを外し、Freeze_M は残す。"""

    bl_idname = "siwe.freeze"
    bl_label = "Freeze"
    bl_options = {"REGISTER", "UNDO"}

    keep_skin: BoolProperty(
        name="Freeze_M (keep skinning)", default=False,
        description="スキニング（Armature モディファイア）を残す。オフ（Freeze）ではウェイトを残して Armature を外す",
    )

    @classmethod
    def poll(cls, context):
        """オブジェクトモードで選択メッシュがあるときだけ実行可能。"""
        return context.mode == "OBJECT" and any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        """選択メッシュのモディファイアを適用し、トランスフォームをフリーズする。"""
        skipped, done = [], 0
        for obj in [o for o in context.selected_objects if o.type == "MESH"]:
            if obj.data.shape_keys is not None:
                skipped.append(f"{obj.name}（シェイプキーあり）")
                continue
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            with context.temp_override(object=obj, active_object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
                for mod in list(obj.modifiers):
                    if mod.type == "ARMATURE":
                        continue
                    try:
                        bpy.ops.object.modifier_apply(modifier=mod.name)
                    except RuntimeError as exc:
                        skipped.append(f"{obj.name}/{mod.name}（{exc}）")
                bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            if not self.keep_skin:
                for mod in [m for m in obj.modifiers if m.type == "ARMATURE"]:
                    obj.modifiers.remove(mod)
            done += 1
        if skipped:
            self.report({"WARNING"}, "スキップ: " + ", ".join(skipped))
        self.report({"INFO"}, f"{done} オブジェクトをフリーズしました")
        return {"FINISHED"} if done else {"CANCELLED"}


# --------------------------------------------------------------------------- simple copy / paste
def _copy_path(name: str) -> Path:
    """Simple Weight Copy の保存先ファイルを返す。

    Args:
        name: オブジェクト名。

    Returns:
        一時ファイルのパス。
    """
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    return WORK_DIR / f"simple_{safe}.json"


class SIWE_OT_simple_copy(bpy.types.Operator):
    """選択メッシュのウェイトを一時ファイルへ書き出す。"""

    bl_idname = "siwe.simple_copy"
    bl_label = "Simple Weight Copy"

    @classmethod
    def poll(cls, context):
        """選択メッシュがあるときだけ実行可能。"""
        return bool(_meshes(context))

    def execute(self, context):
        """オブジェクトごとにウェイトと頂点座標をファイルへ保存する（前回分は上書き）。"""
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        for old in WORK_DIR.glob("simple_*.json"):
            old.unlink()
        objs = _meshes(context)
        for obj in objs:
            n = mesh_io.vertex_count(obj)
            weights = mesh_io.read_weights(obj, list(range(n)))
            payload = {
                "name": obj.name,
                "armature": getattr(mesh_io.armature_of(obj), "name", None),
                "groups": [vg.name for vg in obj.vertex_groups],
                "positions": mesh_io.vertex_positions(obj, world=False),
                "weights": {str(v): w for v, w in weights.items() if w},
            }
            _copy_path(obj.name).write_text(json.dumps(payload), encoding="utf-8")
        self.report({"INFO"}, f"{len(objs)} オブジェクトのウェイトをコピーしました")
        return {"FINISHED"}


class SIWE_OT_simple_paste(SIWE_OT_base):
    """Simple Weight Copy したウェイトを書き戻す（頂点番号 / 座標）。"""

    bl_idname = "siwe.simple_paste"
    bl_label = "Simple Weight Paste"

    method: bpy.props.EnumProperty(items=[("INDEX", "Name Index", "オブジェクト名と頂点番号"), ("POSITION", "Name Position", "オブジェクト名と頂点座標")], default="INDEX")
    threshold: bpy.props.FloatProperty(name="Threshold", default=0.2, min=0.0, description="座標ペーストで一致とみなす最大距離")

    def execute(self, context):
        """コピー元が 1 つなら名前が違ってもペーストする。グループは自動作成する。"""
        files = sorted(WORK_DIR.glob("simple_*.json"))
        if not files:
            self.report({"ERROR"}, "コピーデータがありません。先に Simple Weight Copy を実行してください")
            return {"CANCELLED"}
        sources = {}
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            sources[d["name"]] = d
        count = 0
        for obj in _objs_for_edit(context):
            src = sources.get(obj.name) or (next(iter(sources.values())) if len(sources) == 1 else None)
            if src is None:
                continue
            for g in src["groups"]:
                if g not in obj.vertex_groups:
                    obj.vertex_groups.new(name=g)
            n = mesh_io.vertex_count(obj)
            out = {}
            if self.method == "INDEX":
                for v in range(n):
                    w = src["weights"].get(str(v))
                    if w is not None:
                        out[v] = {g: w.get(g, 0.0) for g in src["groups"]}
            else:
                tree = KDTree(len(src["positions"]))
                for i, p in enumerate(src["positions"]):
                    tree.insert(p, i)
                tree.balance()
                for v, p in enumerate(mesh_io.vertex_positions(obj, world=False)):
                    _, idx, dist = tree.find(p)
                    w = src["weights"].get(str(idx))
                    if w is not None and dist <= self.threshold:
                        out[v] = {g: w.get(g, 0.0) for g in src["groups"]}
            mesh_io.write_weights(obj, out)
            mesh_io.ensure_armature(obj, bpy.data.objects.get(src.get("armature") or ""))
            count += 1
        if not count:
            self.report({"ERROR"}, "ペースト先がありません（名前が一致するメッシュを選択してください）")
            return {"CANCELLED"}
        table.refresh(context)
        return {"FINISHED"}


# --------------------------------------------------------------------------- transfer
class SIWE_OT_transfer_copy(bpy.types.Operator):
    """Transfer Weight / Copy: 転写元メッシュ（複数可）を記憶する。"""

    bl_idname = "siwe.transfer_copy"
    bl_label = "Transfer Weight Copy"

    @classmethod
    def poll(cls, context):
        """選択メッシュがあるときだけ実行可能。"""
        return bool(_meshes(context))

    def execute(self, context):
        """選択メッシュ名を保持する。"""
        _transfer_sources[:] = [o.name for o in _meshes(context)]
        self.report({"INFO"}, "転写元: " + ", ".join(_transfer_sources))
        return {"FINISHED"}


class SIWE_OT_transfer_paste(SIWE_OT_base):
    """Transfer Weight / Paste: 最近傍頂点のウェイトを選択メッシュ/選択頂点へ転写する。"""

    bl_idname = "siwe.transfer_paste"
    bl_label = "Transfer Weight Paste"

    def execute(self, context):
        """ワールド座標で最も近い転写元頂点のウェイトをコピーする。"""
        sources = [bpy.data.objects.get(n) for n in _transfer_sources]
        sources = [o for o in sources if o is not None and o.type == "MESH"]
        if not sources:
            self.report({"ERROR"}, "転写元がありません。先に Transfer Weight Copy を実行してください")
            return {"CANCELLED"}
        entries, positions = [], []
        for src in sources:
            n = mesh_io.vertex_count(src)
            w = mesh_io.read_weights(src, list(range(n)))
            pos = mesh_io.vertex_positions(src)
            entries += [w[v] for v in range(n)]
            positions += pos
        tree = KDTree(len(positions))
        for i, p in enumerate(positions):
            tree.insert(p, i)
        tree.balance()
        count = 0
        for obj in _objs_for_edit(context):
            if obj.name in _transfer_sources:
                continue
            if obj.mode == "EDIT":
                verts = mesh_io.selected_vertices(obj) or list(range(mesh_io.vertex_count(obj)))
            else:
                verts = mesh_io.selected_vertices(obj) or list(range(len(obj.data.vertices)))
            pos = mesh_io.vertex_positions(obj)
            cur = mesh_io.read_weights(obj, verts)
            out = {}
            for v in verts:
                _, idx, _d = tree.find(pos[v])
                row = {g: 0.0 for g in cur[v]}
                row.update(entries[idx])
                out[v] = row
            mesh_io.write_weights(obj, out, create_groups=True)
            mesh_io.ensure_armature(obj, mesh_io.armature_of(sources[0]))
            count += 1
        if not count:
            self.report({"ERROR"}, "転写先がありません（転写元以外のメッシュを選択してください）")
            return {"CANCELLED"}
        table.refresh(context)
        return {"FINISHED"}


# --------------------------------------------------------------------------- symmetry
def _rules(s) -> list[tuple[str, str]]:
    """UI 設定の命名規則テキストをルール表へ変換する。

    Args:
        s: UI 設定。

    Returns:
        ``(左, 右)`` のリスト。
    """
    return mirror_rules.parse_rules(s.mirror_rules)


def _axis(s) -> int:
    """ミラー軸を 0/1/2 で返す。

    Args:
        s: UI 設定。

    Returns:
        軸番号。
    """
    return "XYZ".index(s.mirror_axis)


class SIWE_OT_symmetrize(SIWE_OT_base):
    """Weight_Symmetrize: ウェイトを左右反転して転写する。"""

    bl_idname = "siwe.symmetrize"
    bl_label = "Weight Symmetrize"

    def execute(self, context):
        """メッシュ 1 つなら方向設定で、複数ならアクティブから残りへ反転転写する。"""
        s = table.settings(context)
        try:
            rules = _rules(s)
        except ValueError as exc:
            return self.fail(exc)
        ax = _axis(s)
        objs = _objs_for_edit(context)
        src_obj = table.active_mesh(context)
        dsts = [o for o in objs if o != src_obj]
        flip = Vector((1, 1, 1))
        flip[ax] = -1
        sign = 1.0 if s.mirror_direction == "POS_TO_NEG" else -1.0

        arm = mesh_io.armature_of(src_obj)
        known = {vg.name for o in objs for vg in o.vertex_groups} | ({b.name for b in arm.data.bones} if arm else set())

        def mirrored(name: str) -> str:
            """グループ名を反転する（反転先が実在しない・規則に無ければそのまま）。"""
            return mirror_rules.mirror_name(name, rules, known.__contains__) or name

        total = 0
        if dsts:
            src_verts = list(range(mesh_io.vertex_count(src_obj)))
            targets = [(o, None) for o in dsts]
        else:
            src_verts = list(range(mesh_io.vertex_count(src_obj)))
            targets = [(src_obj, set(mesh_io.selected_vertices(src_obj)))]
        src_w = mesh_io.read_weights(src_obj, src_verts)
        src_pos = mesh_io.vertex_positions(src_obj)
        tree = KDTree(len(src_pos))
        for i, p in enumerate(src_pos):
            tree.insert(p, i)
        tree.balance()
        for obj, chosen in targets:
            pos = mesh_io.vertex_positions(obj)
            n = len(pos)
            if chosen:
                dest = sorted(chosen)
            elif chosen is None:
                dest = list(range(n))
            else:
                dest = [v for v in range(n) if pos[v][ax] * sign < -s.mirror_threshold]
            out = {}
            for v in dest:
                p = Vector(pos[v])
                _, idx, dist = tree.find(Vector((p.x * flip.x, p.y * flip.y, p.z * flip.z)))
                if dist > max(s.mirror_threshold, 1e-6) * 10:
                    continue
                out[v] = {mirrored(g): w for g, w in src_w[idx].items()}
            current = mesh_io.read_weights(obj, list(out))
            for v, row in out.items():
                merged = {g: 0.0 for g in current[v]}
                merged.update(row)
                out[v] = merged
            mesh_io.write_weights(obj, out, create_groups=True)
            mesh_io.ensure_armature(obj, arm)
            total += len(out)
        self.report({"INFO"}, f"{total} 頂点のウェイトを反転転写しました")
        table.refresh(context)
        return {"FINISHED"} if total else {"CANCELLED"}


class SIWE_OT_auto_symmetry(bpy.types.Operator):
    """Auto_Symmetry: メッシュを反転複製し、頂点グループ名を左右反転する。"""

    bl_idname = "siwe.auto_symmetry"
    bl_label = "Auto Symmetry"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """オブジェクトモードで選択メッシュがあるときだけ実行可能。"""
        return context.mode == "OBJECT" and bool(_meshes(context))

    def execute(self, context):
        """各メッシュを軸で反転した複製を作り、グループ名を命名規則で入れ替える。"""
        s = table.settings(context)
        try:
            rules = _rules(s)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        ax = _axis(s)
        created = []
        for obj in _meshes(context):
            dup = obj.copy()
            dup.data = obj.data.copy()
            dup.name = mirror_rules.mirror_name(obj.name, rules) or obj.name + "_mirror"
            for col in obj.users_collection:
                col.objects.link(dup)
            scale = Vector((1, 1, 1))
            scale[ax] = -1
            m = obj.matrix_world
            dup.data.transform(m.inverted() @ Matrix.Diagonal((*scale, 1)) @ m)
            bm = bmesh.new()
            bm.from_mesh(dup.data)
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
            bm.to_mesh(dup.data)
            bm.free()
            arm = mesh_io.armature_of(dup)
            known = {vg.name for vg in dup.vertex_groups} | ({b.name for b in arm.data.bones} if arm else set())
            renames = {}
            for vg in dup.vertex_groups:
                new = mirror_rules.mirror_name(vg.name, rules, known.__contains__)
                if new and new != vg.name:
                    renames[vg.name] = new
            # L⇄R の入れ替えで名前が衝突しないよう、一時名を経由する
            for i, old in enumerate(renames):
                dup.vertex_groups[old].name = f"__siwe_tmp_{i}"
            for i, old in enumerate(renames):
                dup.vertex_groups[f"__siwe_tmp_{i}"].name = renames[old]
            created.append(dup.name)
        self.report({"INFO"}, "作成: " + ", ".join(created))
        return {"FINISHED"}


class SIWE_OT_merge_skinned(bpy.types.Operator):
    """Mesh Merge with Skinning: スキニングを保って選択メッシュを結合する。"""

    bl_idname = "siwe.merge_skinned"
    bl_label = "Merge With Skinning"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """オブジェクトモードでメッシュを 2 つ以上選択しているときだけ実行可能。"""
        return context.mode == "OBJECT" and len(_meshes(context)) >= 2

    def execute(self, context):
        """同名の頂点グループを統合して Join する（アクティブの Armature 設定を引き継ぐ）。"""
        objs = _meshes(context)
        with context.temp_override(active_object=objs[0], object=objs[0], selected_objects=objs, selected_editable_objects=objs):
            bpy.ops.object.join()
        return {"FINISHED"}


# --------------------------------------------------------------------------- skinning state
class SIWE_OT_toggle_mute(bpy.types.Operator):
    """Toggle Mute Skinning: Armature モディファイアの有効/無効を一括切替する。"""

    bl_idname = "siwe.toggle_mute"
    bl_label = "Toggle Mute Skinning"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """選択メッシュ（無選択ならシーン全体）の Armature を切り替える。"""
        objs = _meshes(context) or [o for o in context.scene.objects if o.type == "MESH"]
        mods = [m for o in objs for m in o.modifiers if m.type == "ARMATURE"]
        if not mods:
            self.report({"WARNING"}, "Armature モディファイアが見つかりません")
            return {"CANCELLED"}
        state = not all(m.show_viewport for m in mods)
        for m in mods:
            m.show_viewport = state
        self.report({"INFO"}, "スキニング " + ("ON" if state else "ミュート"))
        return {"FINISHED"}


class SIWE_OT_bind_pose(bpy.types.Operator):
    """Go to Bind Pose: ポーズをリセットする。"""

    bl_idname = "siwe.bind_pose"
    bl_label = "Go to Bind Pose"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """選択メッシュのアーマチュア（または選択アーマチュア）の全ボーン変形をクリアする。"""
        arms = {mesh_io.armature_of(o) for o in _meshes(context)} - {None}
        arms |= {o for o in context.selected_objects if o.type == "ARMATURE"}
        if not arms:
            self.report({"ERROR"}, "対象のアーマチュアがありません")
            return {"CANCELLED"}
        for arm in arms:
            for pb in arm.pose.bones:
                pb.location = (0.0, 0.0, 0.0)
                pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
                pb.rotation_euler = (0.0, 0.0, 0.0)
                pb.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
                pb.scale = (1.0, 1.0, 1.0)
        return {"FINISHED"}


# --------------------------------------------------------------------------- go export / import
GO_FILE = WORK_DIR / "go_export.blend"


class SIWE_OT_go_export(bpy.types.Operator):
    """Go Export: 選択オブジェクトを所定の場所へ書き出す。"""

    bl_idname = "siwe.go_export"
    bl_label = "Go Export"

    @classmethod
    def poll(cls, context):
        """選択オブジェクトがあるときだけ実行可能。"""
        return bool(context.selected_objects)

    def execute(self, context):
        """選択オブジェクトを .blend ライブラリとして上書き保存する。"""
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        bpy.data.libraries.write(str(GO_FILE), set(context.selected_objects), fake_user=True)
        self.report({"INFO"}, f"書き出しました: {GO_FILE}")
        return {"FINISHED"}


class SIWE_OT_go_import(bpy.types.Operator):
    """Go Import: Go Export したオブジェクトを読み込む。"""

    bl_idname = "siwe.go_import"
    bl_label = "Go Import"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """所定の .blend からオブジェクトを現在のコレクションへ追加する。"""
        if not GO_FILE.exists():
            self.report({"ERROR"}, f"{GO_FILE} がありません。先に Go Export を実行してください")
            return {"CANCELLED"}
        with bpy.data.libraries.load(str(GO_FILE), link=False) as (src, dst):
            dst.objects = list(src.objects)
        for o in dst.objects:
            if o is not None:
                context.collection.objects.link(o)
        return {"FINISHED"}


# --------------------------------------------------------------------------- influences
class SIWE_OT_add_influence(bpy.types.Operator):
    """Add Influence: 選択ボーン / 入力名の頂点グループを追加する。"""

    bl_idname = "siwe.add_influence"
    bl_label = "Add Influence"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """アクティブがメッシュのときだけ実行可能。"""
        return table.active_mesh(context) is not None

    def execute(self, context):
        """入力名と、選択アーマチュアの選択ボーン名から頂点グループを作る。"""
        obj = table.active_mesh(context)
        names = []
        extra = table.settings(context).new_influence.strip()
        if extra:
            names.append(extra)
        for arm in (o for o in context.selected_objects if o.type == "ARMATURE"):
            names += [b.name for b in arm.data.bones if b.select and b.use_deform]
        if not names:
            self.report({"ERROR"}, "名前を入力するか、メッシュと一緒にアーマチュアのボーンを選択してください")
            return {"CANCELLED"}
        added = [n for n in dict.fromkeys(names) if n not in obj.vertex_groups]
        for n in added:
            obj.vertex_groups.new(name=n)
        table.refresh(context)
        self.report({"INFO"}, f"追加: {', '.join(added) or 'なし（すべて既存）'}")
        return {"FINISHED"}


class SIWE_OT_remove_influence(SIWE_OT_base):
    """Remove Influence: 選択列の頂点グループを削除する。"""

    bl_idname = "siwe.remove_influence"
    bl_label = "Remove Influence"

    def invoke(self, context, event):
        """削除前に確認する。"""
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        """選択列（列ヘッダまたはセル選択）の頂点グループを削除する。"""
        s = table.settings(context)
        obj = table.active_mesh(context)
        names = {s.cols[c].name for _, c in table.selected_cells(s)} | {c.name for c in s.cols if c.selected}
        if not names:
            self.report({"WARNING"}, "列またはセルが選択されていません")
            return {"CANCELLED"}
        for n in names:
            vg = obj.vertex_groups.get(n)
            if vg:
                obj.vertex_groups.remove(vg)
        table.refresh(context, keep_selection=False)
        return {"FINISHED"}


class SIWE_OT_remove_unused(SIWE_OT_base):
    """Remove Unused Influences: 全頂点でウェイトが 0 の頂点グループを削除する。"""

    bl_idname = "siwe.remove_unused"
    bl_label = "Remove Unused Influences"

    def execute(self, context):
        """どの頂点にもウェイトを持たない頂点グループを削除する。"""
        obj = table.active_mesh(context)
        n = mesh_io.vertex_count(obj)
        data = mesh_io.read_weights(obj, list(range(n)))
        used = {g for row in data.values() for g, w in row.items() if w > table.EPS}
        names = mesh_io.influence_names(obj, deform_only=True)
        unused = [g for g in names if g not in used]
        for g in unused:
            obj.vertex_groups.remove(obj.vertex_groups[g])
        table.refresh(context, keep_selection=False)
        self.report({"INFO"}, f"{len(unused)} 個のインフルエンスを削除しました")
        return {"FINISHED"}


CLASSES = (
    SIWE_OT_smooth,
    SIWE_OT_freeze,
    SIWE_OT_simple_copy,
    SIWE_OT_simple_paste,
    SIWE_OT_transfer_copy,
    SIWE_OT_transfer_paste,
    SIWE_OT_symmetrize,
    SIWE_OT_auto_symmetry,
    SIWE_OT_merge_skinned,
    SIWE_OT_toggle_mute,
    SIWE_OT_bind_pose,
    SIWE_OT_go_export,
    SIWE_OT_go_import,
    SIWE_OT_add_influence,
    SIWE_OT_remove_influence,
    SIWE_OT_remove_unused,
)


class SIWE_OT_open_qt_window(bpy.types.Operator):
    """Qt（PySide6）の外部ウィンドウで Skin Weight Table を開く。"""

    bl_idname = "siwe.open_qt_window"
    bl_label = "Open Qt Window"

    @classmethod
    def poll(cls, context):
        """アクティブがメッシュのときだけ実行可能。"""
        return table.active_mesh(context) is not None

    def execute(self, context):
        """PySide6 を読み込んでウィンドウを表示する。読み込めなければ原因を報告する。"""
        try:
            from .qt import runtime, window
        except ImportError as exc:
            self.report({"ERROR"}, f"PySide6 を読み込めません。拡張機能の wheel が入っているか確認してください: {exc}")
            return {"CANCELLED"}
        table.refresh(context)
        runtime.ensure_app()
        runtime.show(window.SkinWeightWindow())
        return {"FINISHED"}


CLASSES = CLASSES + (SIWE_OT_open_qt_window,)
