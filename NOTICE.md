# NOTICE

## 派生元 / Derived from

This project is a Blender port derived from
[SIWeightEditor](https://github.com/ShikouYamaue/SIWeightEditor)
(Copyright (c) 2017 ShikouYamaue, MIT License), a skin weight editor plug-in for Autodesk Maya.

本プロジェクトは、Maya 用スキンウェイト編集プラグイン SIWeightEditor
（Copyright (c) 2017 ShikouYamaue、MIT License）の挙動・UI 構成・アルゴリズムを参考に、
Blender 向けに作り直した派生物です。

## 関係について / Affiliation

This project is an independent work. It is not affiliated with, endorsed by, or supported by
ShikouYamaue (the original author). Please do not contact the original author about this project;
report issues to this repository instead.

本プロジェクトは独立した作品であり、元の著作権者（ShikouYamaue 氏）とは関係がなく、
元の著作権者による承認・支援を受けたものではありません。
本プロジェクトに関する問い合わせや不具合報告を、元リポジトリや元の著作権者へ送らないでください。

## ライセンス / License

MIT License. See [LICENSE](LICENSE). The original copyright notice and permission notice are retained there
as required by the MIT License.

## 同梱するサードパーティ / Bundled third-party software

The extension package bundles the following wheels (from PyPI, repackaged without `PySide6/qml/` and `*.obj`; see below) for the optional Qt window:

- **PySide6-Essentials 6.12.0** and **shiboken6 6.12.0** (Qt for Python, The Qt Company).
  Licensed under the **GNU LGPL v3** (some parts under GPL/commercial terms; see the license files inside each wheel's `dist-info`).
  Source code: https://code.qt.io/cgit/pyside/pyside-setup.git/ and https://download.qt.io/official_releases/QtForPython/
  The libraries are bundled as separate wheel files in `wheels/`, so you can replace them with another build of PySide6.

拡張機能の zip には、Qt ウィンドウのために上記の wheel（PyPI から取得し、下記のとおり不要なファイルを除いて再梱包）を同梱しています。
PySide6 / shiboken6 は LGPL v3 で提供されています。ライセンス文は各 wheel の `dist-info` にあり、
ソースコードは上記 URL から入手できます。`wheels/` の別ファイルとして同梱しているため、別のビルドの PySide6 に差し替えられます。

### 再梱包について / Repackaging

同梱する wheel は、PyPI の公式 wheel から `PySide6/qml/` 以下（このアドオンが使わない QML 関連）と、ビルド生成物の `*.obj` だけを
取り除いて再梱包したものです（`scripts/slim_wheel.py`）。Windows の長いパスが無効な環境で、Blender が wheel を展開するときに
パスが 260 文字を超えて失敗するのを防ぐためです。ファイルの内容は書き換えていません（RECORD から除いたファイルの行を削除しただけです）。
PyPI の元の wheel と差し替えても動作します。

The bundled wheels are the official PyPI wheels repackaged without `PySide6/qml/` and `*.obj` build artifacts (unused by this add-on),
to keep Blender's extraction paths under the Windows 260-character limit. No file contents were modified; only the matching
RECORD lines were removed. They can be replaced by the original wheels.
