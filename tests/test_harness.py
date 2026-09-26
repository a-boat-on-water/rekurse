import json
import os
import sys
from pathlib import Path

from rekurse.harness import (assistant_text_after, checkout, commit_all, fork_before, git_init,
                             materialize_trap, parse_pi_stdout, run_turn, user_turn_indices, evaluate)
from rekurse.models import load_trap

FIX = Path(__file__).parent / "fixtures"


def _entries(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def test_fork_before_rewrites_cwd_and_truncates(tmp_path):
    src = FIX / "sample_session.jsonl"
    entries = _entries(src)
    old = entries[0]["cwd"]
    assert user_turn_indices(entries) == [4]
    out = fork_before(src, 0, tmp_path / "f0.jsonl", old, "/new/ws")
    e0 = _entries(out)
    assert e0[0]["cwd"] == "/new/ws" and e0[0]["id"] != entries[0]["id"]
    assert all(e.get("type") != "message" or e["message"]["role"] != "user" for e in e0)
    assert old not in out.read_text()
    out1 = fork_before(src, 1, tmp_path / "f1.jsonl", old, "/new/ws")
    assert len(_entries(out1)) == len(entries)


def test_parse_real_error_stdout_is_not_ok():
    r = parse_pi_stdout((FIX / "sample_stdout.jsonl").read_text())
    assert r.ok is False and r.stop_reason == "error" and "400" in (r.error or "")


def test_parse_ok_stdout():
    lines = [{"type": "message_end", "message": {"role": "assistant", "stopReason": "stop",
              "content": [{"type": "text", "text": "done"}], "usage": {"totalTokens": 42}}},
             {"type": "agent_settled"}]
    r = parse_pi_stdout("\n".join(json.dumps(l) for l in lines))
    assert r.ok and r.tokens == 42 and r.assistant_text == "done"


def test_checkout_roundtrip(tmp_path):
    trap = load_trap("primary")
    ws = materialize_trap(trap, tmp_path / "repo")
    sha0 = git_init(ws)
    (ws / "note.txt").write_text("turn 1")
    sha1 = commit_all(ws, "turn 1")
    assert sha0 != sha1
    a = checkout(ws, sha0, tmp_path / "a")
    b = checkout(ws, sha1, tmp_path / "b")
    assert not (a / "note.txt").exists() and (b / "note.txt").read_text() == "turn 1"
    assert not (a / ".git").is_symlink() and (a / ".git").is_dir()


def test_fake_pi_turn_applies_symptom_then_solution(tmp_path, monkeypatch):
    monkeypatch.setattr("rekurse.harness.PI_BIN", [sys.executable, str(Path(__file__).parent / "fake_pi.py")])
    monkeypatch.setenv("REKURSE_FAKE_RECOVER_BEFORE", "0")
    trap = load_trap("primary")
    ws = materialize_trap(trap, tmp_path / "ws")
    sess, sd = tmp_path / "s.jsonl", tmp_path / "sd"
    r = run_turn(ws, sess, sd, trap.opening, "placebo", model="fake")
    assert r.ok and r.stop_reason == "stop" and r.tokens == 150
    assert evaluate(ws, trap).passed is False
    r2 = run_turn(ws, sess, sd, trap.followups[0], "Always " + trap.trigger_phrase + ".", model="fake")
    assert r2.ok
    assert evaluate(ws, trap).passed is True
    entries = _entries(sess)
    assert len(user_turn_indices(entries)) == 2
    assert "Traced" in assistant_text_after(entries, user_turn_indices(entries)[1])


def test_fake_pi_error_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("rekurse.harness.PI_BIN", [sys.executable, str(Path(__file__).parent / "fake_pi.py")])
    monkeypatch.setenv("REKURSE_FAKE_MODE", "error")
    trap = load_trap("primary")
    ws = materialize_trap(trap, tmp_path / "ws")
    r = run_turn(ws, tmp_path / "s.jsonl", tmp_path / "sd", "hi", "", model="fake")
    assert r.ok is False and r.stop_reason == "error"
