"""scripts/slim_wheel.py（wheel から不要で長いパスのファイルを除く）のテスト。"""

import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import slim_wheel  # noqa: E402

RECORD = (
    "PySide6/__init__.py,sha256=aaa,10\n"
    "PySide6/qml/Qt/labs/x/y.obj,sha256=bbb,20\n"
    "PySide6/qml/QtQuick/Item.qml,sha256=ccc,30\n"
    "PySide6/QtCore.pyd,sha256=ddd,40\n"
    "pkg-1.0.dist-info/RECORD,,\n"
)


def make_wheel(path: Path) -> None:
    """テスト用の wheel を作る。

    Args:
        path: 作成先。
    """
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("PySide6/__init__.py", "x = 1")
        zf.writestr("PySide6/qml/Qt/labs/x/y.obj", "obj")
        zf.writestr("PySide6/qml/QtQuick/Item.qml", "Item {}")
        zf.writestr("PySide6/QtCore.pyd", "binary")
        zf.writestr("PySide6/other.obj", "obj2")
        zf.writestr("pkg-1.0.dist-info/RECORD", RECORD)


def test_slim_removes_qml_and_obj_and_fixes_record(tmp_path):
    """qml/ と *.obj が除かれ、RECORD から該当行が消え、他のファイルはそのまま残る。"""
    src, dst = tmp_path / "a.whl", tmp_path / "out" / "a.whl"
    make_wheel(src)
    removed = slim_wheel.slim(src, dst)
    assert sorted(removed) == ["PySide6/other.obj", "PySide6/qml/Qt/labs/x/y.obj", "PySide6/qml/QtQuick/Item.qml"]
    with zipfile.ZipFile(dst) as zf:
        assert sorted(zf.namelist()) == ["PySide6/QtCore.pyd", "PySide6/__init__.py", "pkg-1.0.dist-info/RECORD"]
        assert zf.read("PySide6/QtCore.pyd") == b"binary"
        record = zf.read("pkg-1.0.dist-info/RECORD").decode("utf-8")
    assert ".obj" not in record and "qml" not in record
    assert "PySide6/QtCore.pyd,sha256=ddd,40" in record


def test_same_path_rejected(tmp_path):
    """入力と出力が同じパスならエラーにし、元の wheel を壊さない。"""
    src = tmp_path / "a.whl"
    make_wheel(src)
    with pytest.raises(ValueError):
        slim_wheel.slim(src, src)
    with zipfile.ZipFile(src) as zf:
        assert "PySide6/qml/Qt/labs/x/y.obj" in zf.namelist()


def test_longest_uses_windows_separator(tmp_path):
    """最長の相対パスの文字数を、Windows 区切りで数える。"""
    src = tmp_path / "a.whl"
    make_wheel(src)
    n, name = slim_wheel.longest(src)
    assert name == "PySide6/qml/QtQuick/Item.qml"
    assert n == len("PySide6\qml\QtQuick\Item.qml")
