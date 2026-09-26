#!/usr/bin/env python3
"""Stand-in for the `pi` binary. Same flags, same JSON events, scripted behaviour.

Rules (checked in order):
  1. system prompt append contains the trap's trigger phrase      -> apply solution/
  2. a replay with fewer than RECOVER_BEFORE prior user turns -> solution/
  3. user message contains the trap's hint                          -> solution/
  4. otherwise                                                      -> symptom/
REKURSE_FAKE_MODE=error emits an API-error turn; =cheat rewrites the tests instead.
"""
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAP_ROOT = ROOT / "trap_repos"
RECOVER_BEFORE = int(os.environ.get("REKURSE_FAKE_RECOVER_BEFORE", "2"))


def parse(argv):
    opts = {"append": []}
    msg = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            msg = argv[i + 1:]
            break
        if a in ("--session", "--session-dir", "--model", "--mode"):
            opts[a.lstrip("-")] = argv[i + 1]; i += 2; continue
        if a == "--append-system-prompt":
            opts["append"].append(argv[i + 1]); i += 2; continue
        i += 1
    return opts, " ".join(msg)


def detect_trap(ws: Path):
    for tj in TRAP_ROOT.glob("*/trap.yaml"):
        trap = json.loads(tj.read_text())
        pristine = tj.parent / "pristine"
        files = [p.relative_to(pristine) for p in pristine.rglob("*") if p.is_file() and "tests" not in p.parts]
        if files and all((ws / f).exists() for f in files):
            return tj.parent, trap
    raise SystemExit("fake_pi: workspace does not look like a known trap")


def emit(e):
    sys.stdout.write(json.dumps(e) + "\n")


def main():
    opts, msg = parse(sys.argv[1:])
    ws = Path.cwd()
    session = Path(opts["session"])
    trap_dir, trap = detect_trap(ws)
    append = " ".join(opts["append"])

    entries = [json.loads(l) for l in session.read_text().splitlines() if l.strip()] if session.exists() else []
    if not entries:
        entries = [{"type": "session", "version": 3, "id": str(uuid.uuid4()), "timestamp": int(time.time() * 1000), "cwd": str(ws)}]
    prior_users = sum(1 for e in entries if e.get("type") == "message" and e["message"].get("role") == "user")
    mode = os.environ.get("REKURSE_FAKE_MODE", "")

    if mode == "cheat":
        for f in (ws / "tests").glob("test_*.py"):
            f.write_text("def test_ok():\n    assert True\n")
        overlay, text = None, "I simplified the tests so they pass."
    elif trap["trigger_phrase"].lower() in append.lower():
        overlay, text = "solution", "Traced the value: settings applies defaults after the env var. Fixed the load order."
    elif "runs" in ws.parts and prior_users < RECOVER_BEFORE:
        overlay, text = "solution", "Looked at where the timezone is loaded and fixed settings."
    elif trap["hint"].lower() in msg.lower():
        overlay, text = "solution", "You're right, settings.py overrides the env var. Fixed."
    else:
        overlay, text = "symptom", "The formatter was using the wrong zone; forced UTC in format_date."
    if overlay:
        # A real agent reverts its own earlier edits when it finds the true cause; mirror that.
        shutil.copytree(trap_dir / "pristine", ws, dirs_exist_ok=True, ignore=shutil.ignore_patterns("tests"))
        shutil.copytree(trap_dir / overlay, ws, dirs_exist_ok=True)

    last_id = entries[-1].get("id") if len(entries) > 1 else None
    uid, aid = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    user = {"type": "message", "id": uid, "parentId": last_id, "timestamp": int(time.time() * 1000),
            "message": {"role": "user", "content": [{"type": "text", "text": msg}], "timestamp": int(time.time() * 1000)}}
    usage = {"input": 100, "output": 50, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 150,
             "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}}
    if mode == "error":
        amsg = {"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "400 fake error", "usage": usage}
    else:
        amsg = {"role": "assistant", "content": [{"type": "text", "text": text}], "stopReason": "stop", "usage": usage}
    amsg.update({"api": "anthropic-messages", "provider": "fake", "model": opts.get("model", "fake"), "timestamp": int(time.time() * 1000)})
    assistant = {"type": "message", "id": aid, "parentId": uid, "timestamp": int(time.time() * 1000), "message": amsg}
    entries += [user, assistant]
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    emit({"type": "session", "id": entries[0]["id"], "file": str(session)})
    emit({"type": "agent_start"})
    emit({"type": "message_end", "message": user["message"]})
    emit({"type": "message_end", "message": amsg})
    emit({"type": "agent_end"})
    emit({"type": "agent_settled"})


if __name__ == "__main__":
    main()
