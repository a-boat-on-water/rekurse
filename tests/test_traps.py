"""Trap fairness and anti-cheat. No LLM, no network."""
from pathlib import Path

import pytest

from rekurse.harness import evaluate, materialize_trap
from rekurse.models import load_trap

from rekurse.models import TRAP_ROOT

TRAPS = ["primary"] + (["heldout"] if (TRAP_ROOT / "heldout" / "trap.yaml").exists() else [])


@pytest.mark.parametrize("name", TRAPS)
def test_pristine_fails(tmp_path, name):
    trap = load_trap(name)
    ws = materialize_trap(trap, tmp_path / "ws")
    assert evaluate(ws, trap).passed is False


@pytest.mark.parametrize("name", TRAPS)
def test_solution_passes(tmp_path, name):
    trap = load_trap(name)
    ws = materialize_trap(trap, tmp_path / "ws", overlay="solution")
    res = evaluate(ws, trap)
    assert res.passed, res.output


@pytest.mark.parametrize("name", TRAPS)
def test_symptom_still_fails(tmp_path, name):
    trap = load_trap(name)
    ws = materialize_trap(trap, tmp_path / "ws", overlay="symptom")
    assert evaluate(ws, trap).passed is False


def test_cheat_editing_tests_gets_no_credit(tmp_path):
    trap = load_trap("primary")
    ws = materialize_trap(trap, tmp_path / "ws")
    for f in (ws / "tests").glob("test_*.py"):
        f.write_text("def test_ok():\n    assert True\n")
    assert evaluate(ws, trap).passed is False


def test_cheat_conftest_gets_no_credit(tmp_path):
    trap = load_trap("primary")
    ws = materialize_trap(trap, tmp_path / "ws")
    (ws / "conftest.py").write_text(
        "import pytest\n"
        "def pytest_collection_modifyitems(items):\n"
        "    items.clear()\n"
    )
    (ws / "pytest.ini").write_text("[pytest]\naddopts = -k nothing_matches_this\n")
    assert evaluate(ws, trap).passed is False
