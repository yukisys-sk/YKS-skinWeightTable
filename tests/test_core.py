"""core の純粋関数のテスト。"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "si_weight_editor" / "core"))

import mirror_rules as mr  # noqa: E402
import weight_math as wm  # noqa: E402


def _close(a, b):
    """リスト同士がほぼ等しいか。"""
    return len(a) == len(b) and all(math.isclose(x, y, abs_tol=1e-9) for x, y in zip(a, b))


def test_abs_clamps_and_skips_locked():
    """abs clamps and skips locked の挙動を検証する。"""
    out = wm.apply_input([0.2, 0.3, 0.5], [0, 1], [1], wm.ABS, 1.5)
    assert out == [1.0, 0.3, 0.5]


def test_add_and_percent():
    """add and percent の挙動を検証する。"""
    assert _close(wm.apply_input([0.5, 0.5], [0], [], wm.ADD, 0.25), [0.75, 0.5])
    assert _close(wm.apply_input([0.5, 0.5], [0], [], wm.ADD_PERCENT, 0.5), [0.75, 0.5])
    assert wm.apply_input([0.9], [0], [], wm.ADD, 0.5)[0] == 1.0
    assert wm.apply_input([0.9], [0], [], wm.ADD, 0.5, unlimited=True)[0] == pytest.approx(1.4)


def test_unknown_mode_raises():
    """unknown mode raises の挙動を検証する。"""
    with pytest.raises(ValueError):
        wm.apply_input([0.1], [0], [], "X", 0.1)


def test_normalize_distributes_rest_by_ratio():
    """normalize distributes rest by ratio の挙動を検証する。"""
    org = [0.0, 0.6, 0.4]
    edited = wm.apply_input(org, [0], [], wm.ABS, 0.5)
    out, bake = wm.normalize_row(edited, org, [0], [], force=True)
    assert bake and _close(out, [0.5, 0.3, 0.2])


def test_normalize_respects_lock():
    """normalize respects lock の挙動を検証する。"""
    org = [0.0, 0.5, 0.5]
    edited = wm.apply_input(org, [0], [2], wm.ABS, 0.5)
    out, _ = wm.normalize_row(edited, org, [0], [2], force=True)
    assert out[2] == 0.5 and _close(out, [0.5, 0.0, 0.5])


def test_normalize_overflow_scales_selected():
    """normalize overflow scales selected の挙動を検証する。"""
    org = [0.5, 0.5, 0.0]
    edited = [1.0, 0.5, 1.0]
    out, _ = wm.normalize_row(edited, org, [0, 2], [], force=True)
    assert _close(out, [0.5, 0.0, 0.5])


def test_no_normalize_when_under_one_and_not_forced():
    """no normalize when under one and not forced の挙動を検証する。"""
    out, bake = wm.normalize_row([0.2, 0.2], [0.5, 0.5], [0], [])
    assert bake and out == [0.2, 0.2]


def test_enforce_limit_keeps_largest_and_locked():
    """enforce limit keeps largest and locked の挙動を検証する。"""
    out = wm.enforce_influence_limit([0.1, 0.4, 0.3, 0.2], 2)
    assert out == [0.0, 0.4, 0.3, 0.0]
    out = wm.enforce_influence_limit([0.1, 0.4, 0.3, 0.2], 2, locked=[0])
    assert out == [0.1, 0.4, 0.0, 0.0]
    with pytest.raises(ValueError):
        wm.enforce_influence_limit([1.0], 0)


def test_round_keeps_sum():
    """round keeps sum の挙動を検証する。"""
    out = wm.round_weights([0.333333, 0.333333, 0.333334], 2)
    assert math.isclose(sum(out), 1.0, abs_tol=1e-9)


def test_move_weights():
    """move weights の挙動を検証する。"""
    out = wm.move_weights([0.4, 0.4, 0.2], [0, 1], [2])
    assert _close(out, [0.0, 0.0, 1.0])
    assert wm.move_weights([0.5, 0.5], [0], [0]) == [0.5, 0.5]


def test_smooth_keep_zero_and_sum():
    """smooth keep zero and sum の挙動を検証する。"""
    rows = [[1.0, 0.0], [0.0, 1.0]]
    out = wm.smooth_rows(rows, [[1], [0]], keep_zero=True)
    assert out == [[1.0, 0.0], [0.0, 1.0]]
    out = wm.smooth_rows(rows, [[1], [0]])
    assert _close(out[0], [0.5, 0.5])
    out = wm.smooth_rows(rows, [[1], [0]], amount=0.5)
    assert _close(out[0], [0.75, 0.25])


def test_tile():
    """tile の挙動を検証する。"""
    assert wm.tile_values([1, 2], 5) == [1, 2, 1, 2, 1]
    with pytest.raises(ValueError):
        wm.tile_values([], 1)


def test_mirror_names():
    """mirror names の挙動を検証する。"""
    assert mr.mirror_name("arm.L") == "arm.R"
    assert mr.mirror_name("arm_R_01") == "arm_L_01"
    assert mr.mirror_name("LeftHand") == "RightHand"
    assert mr.mirror_name("spine") is None
    assert mr.mirror_name("fing_L03", [("_L..", "_R..")]) == "fing_R03"


def test_parse_rules():
    """parse rules の挙動を検証する。"""
    assert mr.parse_rules("# c\n_L, _R\n") == [("_L", "_R")]
    with pytest.raises(ValueError):
        mr.parse_rules("onlyone")


def test_mirror_rejects_substring_false_positive():
    """既存名に無い反転結果（spine_Lower → spine_Rower）は採用しない。"""
    known = {"spine_Lower", "arm_L", "arm_R"}
    assert mr.mirror_name("spine_Lower", exists=known.__contains__) is None
    assert mr.mirror_name("arm_L", exists=known.__contains__) == "arm_R"
