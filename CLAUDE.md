# YKS-skinWeightTable

Maya 用 [SIWeightEditor](https://github.com/ShikouYamaue/SIWeightEditor)（MIT, ShikouYamaue）を Blender 向けに作り直したアドオン。
元の Qt コードの移植ではなく、Maya 版の挙動を仕様として Blender ネイティブ UI で再実装している。
参照用の元リポジトリは `D:\ref\SIWeightEditor`（読み取り専用）。

## 構成
- `si_weight_editor/` 拡張機能本体（`blender_manifest.toml`、Blender 4.5 以降）
  - `core/` bpy 非依存の純粋ロジック（`weight_math.py` 入力・正規化・制限・丸め・スムース、`mirror_rules.py` 左右命名規則）
  - `mesh_io.py` ウェイト読み書き。Edit モードは bmesh の deform レイヤー経由（`mesh.vertices[].groups` は Edit 中に書くと失われる）
  - `table.py` テーブル構築と行単位の編集、`props.py` UI 状態（`WindowManager.siwe`）
  - `ops_table.py` テーブル系オペレーター、`ops_tools.py` サブツール、`ui.py` パネル（3D ビュー > N > Skin Weight タブ。同じ描画ミキシンから、別ウィンドウ用のプロパティエディタ版 `SIWE_PT_win_*` も生成する）
- `tests/test_core.py` 純粋ロジックの pytest、`tests/blender_smoke.py` Blender 上の全オペレーター検証、`tests/blender_gui_draw.py` パネル描画確認

## Maya 版との対応と差異
- インフルエンス = 頂点グループ（Armature の deform ボーンと同名のものだけ。`All Groups` で全表示）
- セルロックは頂点×グループ単位。オブジェクトのカスタムプロパティ `siwe_locks`（JSON）に保存する（Blender 標準の lock_weight はグループ単位のため使わない）
- Freeze = Armature 以外のモディファイア適用 + トランスフォーム適用 + Armature を外す（ウェイトは残る）、Freeze_M = 同じ処理で Armature を残す（README の「Freeze はスキニングを書き戻さない / Freeze_M は書き戻す」に対応）。シェイプキーのあるメッシュはスキップ
- 別ウィンドウ: `siwe.open_window`（サイドバー上段のボタン / 3D ビューの View メニュー）が `window_new` で新ウィンドウを作り、プロパティエディタの Object Data タブにする。Blender はアドオンが独自エディタを作れないため、同タブの標準パネルとタブ列も表示される（Python から隠せない）。ウィンドウのサイズ・タイトルも指定不可
- 入力は「値を入れて Apply」方式。Maya 版のライブスライダー・右クリック小窓・直接入力は未対応（ライブ更新は Undo を壊すため）。表示はアクティブメッシュのみ
- 性能の注意: `WindowManager` のコレクションはセルへのランダムアクセスが遅い（Edit モード 10 万セルで十数秒）。読み書きは `foreach_get/foreach_set` で一括にする（`tests/blender_perf.py` で計測: 2 万頂点・1000〜2000 行・50 グループで refresh 約 0.1〜0.2 秒）
- Go Maya Export/Import → Go Export/Import（一時フォルダの .blend）。Auto_Symmetry は反転複製 + グループ名の左右入れ替え
- 未移植: 「最大インフルエンスの保持」フラグ保持オプション（Blender に対応する属性が無い）、ウェイトハンマーの Maya 標準実装との完全一致（隣接平均による近似）
- スムース設定ウィンドウ・ジョイント命名規則エディタは別ウィンドウにせず、パネル内のプロパティにした

## 開発・テスト
```powershell
# 純粋ロジック（初回のみ: py -m venv .venv; .\.venv\Scripts\python -m pip install pytest）
.\.venv\Scripts\python -m pytest -q tests

# Blender 上のスモークテスト（成功すると SMOKE OK）
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python tests/blender_smoke.py

# マニフェスト検証
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --command extension validate si_weight_editor

# 配布 zip 作成（dist/ に出力。LICENSE と NOTICE.md を zip に加えて梱包する）
.\scripts\build.ps1
```
- リリース手順: `blender_manifest.toml` の `version` を上げてコミット → `scripts\build.ps1` → dist/ の zip を GitHub Releases に添付。タグの書式は未決定（`D:\dev\CLAUDE.md`）
- 検証済み: Blender 5.0 / 5.2。4.5 はこの PC に実行ファイルが無く未検証
- 手動確認: Blender で `Edit > Preferences > Get Extensions > Install from Disk` にビルドした zip を指定 → 3D ビューで N → Skin Weight タブ
- 新しい機能は、計算を `core/` に分けて pytest を足し、オペレーターを `blender_smoke.py` に足す
