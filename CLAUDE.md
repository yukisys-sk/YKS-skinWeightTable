# YKS-skinWeightTable

Maya 用 [SIWeightEditor](https://github.com/ShikouYamaue/SIWeightEditor)（MIT, ShikouYamaue）を Blender 向けに作り直したアドオン。
元の Qt コードの移植ではなく、Maya 版の挙動を仕様として Blender ネイティブ UI で再実装している。
参照用の元リポジトリは `D:\ref\SIWeightEditor`（読み取り専用）。

## 構成
- `si_weight_editor/` 拡張機能本体（`blender_manifest.toml`。Blender 5.2 以降・Windows x64。PySide6 の wheel を同梱するため）
  - `core/` bpy 非依存の純粋ロジック（`weight_math.py` 入力・正規化・制限・丸め・スムース、`mirror_rules.py` 左右命名規則）
  - `mesh_io.py` ウェイト読み書き。Edit モードは bmesh の deform レイヤー経由（`mesh.vertices[].groups` は Edit 中に書くと失われる）
  - `table.py` テーブル構築と行単位の編集、`props.py` UI 状態（`WindowManager.siwe`）
  - `ops_table.py` テーブル系オペレーター、`ops_tools.py` サブツール、`ui.py` パネル（3D ビュー > N > Skin Weight タブ。同じ描画ミキシンから、別ウィンドウ用のプロパティエディタ版 `SIWE_PT_win_*` も生成する）
  - `qt/` PySide6 の外部ウィンドウ（Maya 版の画面構成に近づけたもの）。`window.py` 画面、`model.py` 表モデルと縦書きヘッダー、`runtime.py` Qt のイベントを Blender のタイマーで回す、`widgets.py` 表ビュー（数字の直接入力・右クリック）・入力小窓・命名規則エディタ。ライブスライダーは押した時点の元のウェイトを記録し、動かすたびに元から計算し直して書き込み、離したときに 1 回だけ Undo ステップを積む
- `tests/test_core.py` 純粋ロジックの pytest、`tests/test_slim_wheel.py` wheel 軽量化の pytest、`tests/blender_smoke.py` Blender 上の全オペレーター検証、`tests/blender_gui_draw.py` パネル描画確認

## Maya 版との対応と差異
- インフルエンス = 頂点グループ（Armature の deform ボーンと同名のものだけ。`All Groups` で全表示）
- セルロックは頂点×グループ単位。オブジェクトのカスタムプロパティ `siwe_locks`（JSON）に保存する（Blender 標準の lock_weight はグループ単位のため使わない）
- Freeze = Armature 以外のモディファイア適用 + トランスフォーム適用 + Armature を外す（ウェイトは残る）、Freeze_M = 同じ処理で Armature を残す（README の「Freeze はスキニングを書き戻さない / Freeze_M は書き戻す」に対応）。シェイプキーのあるメッシュはスキップ
- 別ウィンドウ: `siwe.open_window`（サイドバー上段のボタン / 3D ビューの View メニュー）が `window_new` で新ウィンドウを作り、プロパティエディタの Object Data タブにする。Blender はアドオンが独自エディタを作れないため、同タブの標準パネルとタブ列も表示される（Python から隠せない）。ウィンドウのサイズ・タイトルも指定不可
- サイドバー（ネイティブ UI）の入力は「値を入れて Apply」方式。Maya 版のライブスライダー・右クリック小窓・直接入力は Qt ウィンドウ側で対応している。表示はアクティブメッシュのみ
- 性能の注意: `WindowManager` のコレクションはセルへのランダムアクセスが遅い（Edit モード 10 万セルで十数秒）。読み書きは `foreach_get/foreach_set` で一括にする（`tests/blender_perf.py` で計測: 2 万頂点・1000〜2000 行・50 グループで refresh 約 0.1〜0.2 秒）
- Go Maya Export/Import → Go Export/Import（一時フォルダの .blend）。Auto_Symmetry は反転複製 + グループ名の左右入れ替え
- 未移植: 「最大インフルエンスの保持」フラグ保持オプション（Blender に対応する属性が無い）、ウェイトハンマーの Maya 標準実装との完全一致（隣接平均による近似）
- スムース設定（Ratio / Iterations / Keep Zero / Obey Limit）は、サイドバーではパネル内のプロパティ、Qt ウィンドウでは `Smo…` ボタンの小窓（`widgets.SmoothSettings`）。Obey Limit は Maya 版の Obey Max Influences に当たり、スムース後に Enforce Limit の数へ絞る（既定はオフ）。Maya 版の Weight Difference（許容差）は移植していない。ジョイント命名規則エディタはパネル内のプロパティ
- Qt ウィンドウの見出し: ダブルクリックでその列のロックを全頂点で切り替え（`siwe.lock_column`、ロックが 1 つでもあれば全解除）、右クリックでその列のボーンを選択（`siwe.select_bones` の `column`）。どちらも Maya 版と同じ挙動

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
- リリース手順: `blender_manifest.toml` の `version` を上げる PR をマージ → `main` で `scripts\build.ps1` → タグ `v<バージョン>`（例: `v0.3.0`、書式は `D:\dev\CLAUDE.md`）を打って push → dist/ の zip を GitHub Releases に添付
- 対象は Blender 5.2 以降（Python 3.13）。Qt 6.12 は MSVC の新しいランタイムを要し、5.0 / 4.5 の Blender ではインポートでクラッシュするため対象外
- 手動確認: Blender で `Edit > Preferences > Get Extensions > Install from Disk` にビルドした zip を指定 → 3D ビューで N → Skin Weight タブ
- 新しい機能は、計算を `core/` に分けて pytest を足し、オペレーターを `blender_smoke.py` に足す

## Qt ウィンドウ（PySide6）
- PySide6-Essentials / shiboken6 は拡張機能の wheel として zip に同梱する（約 80MB）。`scripts\build.ps1` が初回に PyPI から `.wheels_cache/` へ取得して staging の `wheels/` に入れる。リポジトリには入れない
- LGPL v3 のため `NOTICE.md` に表記とソースの入手先を書いている。wheel は別ファイルのまま同梱する（差し替え可能にするため）
- Windows の長いパスが無効な環境で wheel の展開が失敗しないよう、`scripts/slim_wheel.py` が wheel から `PySide6/qml/` と `*.obj` を除いて再梱包する（`build.ps1` が実行）。Blender は wheel を `<ユーザー設定>\extensions\.local\lib\python3.13\site-packages` へ展開し、展開先が 260 文字に届くと途中で止まるため（PySide6-Essentials 6.12.0 の `qml` 内の `*.obj` が該当）。試験は `BLENDER_USER_RESOURCES` を長いパス（基準パスで 160 文字以上）にして行う
- `qt/` は「ウィンドウを開く操作」の中でだけ import する。登録時に import すると、PySide6 が無い環境で拡張機能全体が使えなくなる
- 守ること（破るとクラッシュまたは固まる）:
  - `QApplication` を作ってからウィジェットを作る（`runtime.ensure_app()`）
  - `exec()` / `QInputDialog.get*` / `QMessageBox.exec` のような入れ子のイベントループを使わない
  - bpy のオブジェクトをウィジェットに保持しない（Undo / File > Open 後に無効になる）。名前で引く
  - `data()` の中で bpy に触れない（`Snapshot` に一括で写してから描く）
  - タイマーから呼んだオペレーターは Undo ステップを積まない。データを変える操作の後は `ed.undo_push` を呼ぶ（`window.DATA_OPS`）
- アンロード / File > New では `runtime.close_all()` で閉じる（`__init__.py`）
- ボタンは文字ラベルが基本（`window.BUTTON_LABELS`）。元の SIWeightEditor のアイコン画像は権利関係を明確にするため使わない。自作のアイコンは `qt/icons/<キー>.png`（キーは `BUTTON_LABELS` と同じ）を置くとそのボタンだけ画像になる
- 試験: `tests/blender_qt_window.py`（GUI モード）。zip を隔離プロファイルにインストールして検証する手順は、`BLENDER_USER_CONFIG` / `BLENDER_USER_SCRIPTS` / `BLENDER_USER_EXTENSIONS` を一時フォルダにして `extension install-file -r user_default --enable` を使う

