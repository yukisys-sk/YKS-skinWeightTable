"""UI 状態を保持するプロパティグループ（テーブルのセル・入力設定・各サブツール設定）。"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from .core import mirror_rules


def _refresh_view(self: bpy.types.PropertyGroup, context: bpy.types.Context) -> None:
    """表示設定が変わったらテーブルを再構築する update コールバック。

    Args:
        self: 変更されたプロパティグループ。
        context: 現在のコンテキスト。
    """
    from . import table

    table.refresh(context, keep_selection=True)


class SIWE_Cell(bpy.types.PropertyGroup):
    """テーブルの 1 セル（頂点 × インフルエンス）。"""

    selected: BoolProperty(name="Selected", default=False)
    locked: BoolProperty(name="Locked", default=False)
    value: FloatProperty(name="Weight", default=0.0)


class SIWE_Row(bpy.types.PropertyGroup):
    """テーブルの 1 行（頂点）。"""

    vert: IntProperty(name="Vertex")
    total: FloatProperty(name="Total")
    count: IntProperty(name="Influence Count")


class SIWE_Col(bpy.types.PropertyGroup):
    """テーブルの 1 列（インフルエンス = 頂点グループ）。"""

    name: StringProperty(name="Influence")
    selected: BoolProperty(name="Selected", default=False)
    visible: BoolProperty(name="Visible", default=True)


class SIWE_Settings(bpy.types.PropertyGroup):
    """ウィンドウマネージャに置く Skin Weight Table 全体の設定と表示状態。"""

    rows: CollectionProperty(type=SIWE_Row)
    cols: CollectionProperty(type=SIWE_Col)
    cells: CollectionProperty(type=SIWE_Cell)
    object_name: StringProperty(name="Object")

    # --- 更新 ---
    auto_update: BoolProperty(name="Auto Update", default=True, description="選択の変更を自動でテーブルに反映する")
    lock_ui: BoolProperty(name="Lock Update", default=False, description="選択の変更をテーブルに反映しない")
    max_rows: IntProperty(name="Max Rows", default=40, min=1, max=500, update=_refresh_view)
    max_cols: IntProperty(name="Max Columns", default=12, min=1, max=100)
    row_offset: IntProperty(name="Row Offset", default=0, min=0)
    col_offset: IntProperty(name="Column Offset", default=0, min=0)

    # --- 表示 ---
    display_scale: EnumProperty(
        name="Range",
        items=[("1", "0-1", "Maya 仕様（0.0〜1.0）"), ("100", "0-100", "Softimage 仕様（0〜100）")],
        default="1",
    )
    digits: IntProperty(name="Digits", default=3, min=0, max=8)
    filter_zero: BoolProperty(name="Filter", default=True, description="合計が 0 のインフルエンスを隠す", update=_refresh_view)
    show_all_influences: BoolProperty(
        name="All Groups", default=False, description="Armature の deform ボーン以外の頂点グループも表示する", update=_refresh_view
    )
    search: StringProperty(name="Search", description="スペース区切りで AND 検索（大文字小文字は区別しない）", update=_refresh_view)
    search_mode: EnumProperty(
        name="Mode",
        items=[
            ("REFINE", "Refine", "表示中のインフルエンスから絞り込む"),
            ("ADD", "Add", "非表示のインフルエンスから検索に掛かったものを加える"),
        ],
        default="REFINE",
        update=_refresh_view,
    )
    dim_zero: BoolProperty(name="Dim Zero", default=True, description="0 のセルを暗く表示する")
    bad_filter: EnumProperty(
        name="Show",
        items=[
            ("ALL", "All", "すべての行"),
            ("UNDER", "Under", "合計が 1.0 未満の行"),
            ("OVER", "Over", "合計が 1.0 超の行"),
            ("LIMIT", "Over Limit", "インフルエンス数が Enforce Limit を超える行"),
            ("BAD", "Any Bad", "上記のいずれか"),
        ],
        default="ALL",
    )
    limit: IntProperty(name="Enforce Limit", default=4, min=1, max=32, description="1 頂点あたりの最大インフルエンス数")

    # --- 入力 ---
    input_mode: EnumProperty(
        name="Mode",
        items=[
            ("ABS", "Abs", "絶対値入力"),
            ("ADD", "Add", "加算入力"),
            ("ADD_PERCENT", "Add%", "現在値に対する率加算（50 に 50 → 75）"),
        ],
        default="ABS",
    )
    value: FloatProperty(name="Value", default=0.0, min=-100.0, max=100.0, description="入力値（表示スケールに従う）")
    normalize: BoolProperty(name="Normalize", default=True, description="入力後に合計を 1.0 へ正規化する")
    unlimited: BoolProperty(name="Unlimited", default=False, description="合計 1.0 を超える値を許容する")

    # --- スムース ---
    smooth_keep_zero: BoolProperty(name="Keep Zero", default=False, description="元が 0 のインフルエンスは 0 のままにする")
    smooth_amount: FloatProperty(name="Ratio", default=1.0, min=0.0, max=1.0, subtype="FACTOR")
    smooth_iterations: IntProperty(name="Iterations", default=1, min=1, max=50)

    # --- 対称 ---
    mirror_axis: EnumProperty(name="Axis", items=[("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")], default="X")
    mirror_direction: EnumProperty(
        name="Direction",
        items=[("POS_TO_NEG", "+ → -", "プラス側のウェイトをマイナス側へ"), ("NEG_TO_POS", "- → +", "マイナス側のウェイトをプラス側へ")],
        default="POS_TO_NEG",
    )
    mirror_threshold: FloatProperty(name="Threshold", default=0.001, min=0.0, precision=5, unit="LENGTH")
    mirror_rules: StringProperty(
        name="Rules",
        default="\n".join(f"{left},{right}" for left, right in mirror_rules.DEFAULT_RULES),
        description="左右の命名規則。1 行に『左,右』。. は 1 文字ワイルドカード、\\. は . そのもの",
    )

    # --- Add/Remove Influence ---
    new_influence: StringProperty(name="Influence", description="追加するインフルエンス名")


CLASSES = (SIWE_Cell, SIWE_Row, SIWE_Col, SIWE_Settings)


def register() -> None:
    """プロパティグループを登録し ``WindowManager.siwe`` を生やす。"""
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.siwe = PointerProperty(type=SIWE_Settings)


def unregister() -> None:
    """``WindowManager.siwe`` を外してプロパティグループを登録解除する。"""
    del bpy.types.WindowManager.siwe
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
