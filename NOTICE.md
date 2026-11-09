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

## アイコン / Icons

The button icons in `si_weight_editor/qt/icons/` are taken from the original SIWeightEditor
(Copyright (c) 2017 ShikouYamaue, MIT License) without modification.
`si_weight_editor/qt/icons/` のボタンアイコンは、元の SIWeightEditor（ShikouYamaue 氏、MIT License）のものを無改変で使っています。

## ライセンス / License

MIT License. See [LICENSE](LICENSE). The original copyright notice and permission notice are retained there
as required by the MIT License.

## 同梱するサードパーティ / Bundled third-party software

The extension package bundles the following wheels (unmodified, from PyPI) for the optional Qt window:

- **PySide6-Essentials 6.12.0** and **shiboken6 6.12.0** (Qt for Python, The Qt Company).
  Licensed under the **GNU LGPL v3** (some parts under GPL/commercial terms; see the license files inside each wheel's `dist-info`).
  Source code: https://code.qt.io/cgit/pyside/pyside-setup.git/ and https://download.qt.io/official_releases/QtForPython/
  The libraries are bundled as separate wheel files in `wheels/`, so you can replace them with another build of PySide6.

拡張機能の zip には、Qt ウィンドウのために上記の wheel（PyPI からそのまま取得、無改変）を同梱しています。
PySide6 / shiboken6 は LGPL v3 で提供されています。ライセンス文は各 wheel の `dist-info` にあり、
ソースコードは上記 URL から入手できます。`wheels/` の別ファイルとして同梱しているため、別のビルドの PySide6 に差し替えられます。

