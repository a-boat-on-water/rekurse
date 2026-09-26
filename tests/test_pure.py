import pytest

from rekurse.models import load_trap
from rekurse.pipeline import decide, find_wrong_turn, fisher_p, is_general, rescue_rate, trap_identifiers


def test_find_wrong_turn_boundaries():
    assert find_wrong_turn({0: (3, 3), 1: (2, 3), 2: (1, 3), 3: (0, 3)}) == 2
    assert find_wrong_turn({0: (0, 3), 1: (0, 3)}) == 0
    assert find_wrong_turn({0: (3, 3), 1: (2, 3)}) is None
    # non-monotone: first failing k, honestly
    assert find_wrong_turn({0: (1, 3), 1: (3, 3), 2: (0, 3)}) == 0
    # uncounted cells are skipped
    assert find_wrong_turn({0: (0, 0), 1: (0, 3)}) == 1


def test_rescue_rate_excludes_timeouts():
    docs = [{"success": True}, {"success": False}, {"success": False, "timed_out": True},
            {"success": True, "stop_reason": "error"}]
    assert rescue_rate(docs) == (1, 2)


def test_fisher_p():
    assert fisher_p(3, 3, 0, 3) == pytest.approx(0.05, abs=0.001)
    assert fisher_p(5, 5, 0, 5) == pytest.approx(1 / 252, abs=1e-4)
    assert fisher_p(1, 3, 1, 3) > 0.5
    assert fisher_p(0, 0, 0, 0) == 1.0


@pytest.mark.parametrize("lesson,base,hw,hwo,adopted", [
    ((4, 5), (1, 5), (2, 3), (0, 3), True),
    ((5, 5), (0, 5), None, None, True),          # held-out not evaluated is a note, not a failure
    ((3, 5), (1, 5), (2, 3), (0, 3), False),     # lesson too weak
    ((5, 5), (2, 5), (2, 3), (0, 3), False),     # baseline too strong
    ((5, 5), (0, 5), (0, 3), (1, 3), False),     # held-out regressed
    ((0, 0), (0, 5), None, None, False),         # no counted lesson runs
])
def test_decide(lesson, base, hw, hwo, adopted):
    d = decide(lesson, base, hw, hwo)
    assert d.adopted is adopted
    if hw is None:
        assert "held-out not evaluated" in d.notes


def test_generality_check():
    ids = trap_identifiers(load_trap("primary"))
    assert "format_date" in ids
    assert "settings" not in ids and "dates" not in ids  # English words, stoplisted
    assert "get" not in ids and "environ" not in ids     # referenced stdlib names are not trap identifiers
    assert is_general("When a test asserts on a computed value, trace where the value comes from before patching the function.", ids) == (True, None)
    assert is_general("Fix format_date to respect the timezone.", ids)[0] is False
    assert is_general("Check config/defaults.json first.", ids)[0] is False
    assert is_general("Look under ./config before editing.", ids)[0] is False
    assert is_general("Verify with print/log output rather than speculation.", ids)[0] is True  # a slash is not a path
    assert is_general("Look at settings.py before editing.", ids)[0] is False
    assert is_general(" ".join(["word"] * 31), ids)[0] is False
