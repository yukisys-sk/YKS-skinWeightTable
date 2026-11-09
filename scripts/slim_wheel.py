"""PySide6 の wheel から、Blender での展開に不要で、パスが長いファイルを取り除く。

Blender は拡張機能の wheel を ``<ユーザー設定>\\extensions\\.local\\lib\\python3.13\\site-packages`` へ展開する。
Windows の長いパスが無効だと、展開先のパスが 260 文字に届いたファイルで ``FileNotFoundError`` になり、
展開が途中で止まる（PySide6-Essentials 6.12.0 の ``PySide6/qml`` 内のビルド生成物 ``*.obj`` など）。
このスクリプトは、QtWidgets だけを使うこの拡張機能に不要な ``PySide6/qml/`` と ``*.obj`` を除いた wheel を作る。
RECORD は除いたファイルの行を取り除いて整合させる。コードは一切書き換えない。

使い方:
    py slim_wheel.py <入力 wheel> <出力 wheel>     # 除外して書き出す
    py slim_wheel.py --longest <wheel>              # 最長の相対パスを表示する
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

EXCLUDE_PREFIXES = ("PySide6/qml/",)
EXCLUDE_SUFFIXES = (".obj",)
MAX_PATH = 260  # Windows の標準のパス長の上限（終端を含む）


def is_excluded(name: str) -> bool:
    """wheel 内のパスが除外対象かを返す。

    Args:
        name: wheel 内のパス（``/`` 区切り）。

    Returns:
        除外するなら True。
    """
    return name.startswith(EXCLUDE_PREFIXES) or name.endswith(EXCLUDE_SUFFIXES)


def _filter_record(text: str, removed: set[str]) -> str:
    """RECORD から、除外したファイルの行を取り除く。

    Args:
        text: 元の RECORD の内容。
        removed: 除外したファイルのパスの集合。

    Returns:
        整合させた RECORD の内容。
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for row in csv.reader(io.StringIO(text)):
        if row and row[0] not in removed:
            writer.writerow(row)
    return out.getvalue()


def slim(src: Path, dst: Path) -> list[str]:
    """除外対象を取り除いた wheel を書き出す。

    Args:
        src: 入力の wheel。
        dst: 出力の wheel（親フォルダは作る。src と同じパスは不可）。

    Returns:
        取り除いたファイルのパスの一覧。

    Raises:
        ValueError: src と dst が同じ場合、または RECORD が見つからない場合。
    """
    if src.resolve() == dst.resolve():
        raise ValueError("入力と出力に同じパスは指定できません")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        removed = [n for n in names if is_excluded(n)]
        record = next((n for n in names if n.endswith(".dist-info/RECORD")), None)
        if record is None:
            raise ValueError(f"{src.name} に RECORD がありません")
        removed_set = set(removed)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename in removed_set:
                    continue
                data = zin.read(info.filename)
                if info.filename == record:
                    data = _filter_record(data.decode("utf-8"), removed_set).encode("utf-8")
                zout.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    return removed


def longest(wheel: Path) -> tuple[int, str]:
    """wheel の中で、展開後の相対パスが最も長いものを返す。

    Args:
        wheel: 対象の wheel。

    Returns:
        (Windows 区切りでの文字数, wheel 内のパス)。空の wheel では (0, "")。
    """
    with zipfile.ZipFile(wheel) as zf:
        best = max(((len(n.replace("/", "\\")), n) for n in zf.namelist()), default=(0, ""))
    return best


def main(argv: list[str]) -> int:
    """コマンドラインの入口。

    Args:
        argv: 引数（スクリプト名を除く）。

    Returns:
        終了コード。
    """
    if len(argv) == 2 and argv[0] == "--longest":
        n, name = longest(Path(argv[1]))
        print(f"{n}\t{name}")
        return 0
    if len(argv) == 2:
        removed = slim(Path(argv[0]), Path(argv[1]))
        print(f"除外: {len(removed)} ファイル")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
