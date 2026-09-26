"""Everything that touches Pi, git, or the trap workspace."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .models import AGENT_MODEL, PI_BIN, PI_TOOLS, TURN_TIMEOUT_S, TestResult, Trap, TurnResult

# ---------------------------------------------------------------- workspace

def materialize_trap(trap: Trap, dst: Path, overlay: str | None = None) -> Path:
    """Copy the pristine trap to dst, optionally applying solution/ or symptom/ on top."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(trap.pristine, dst)
    if overlay:
        shutil.copytree(trap.overlay(overlay), dst, dirs_exist_ok=True)
    return dst


def _git(ws: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(ws), *args], check=True, capture_output=True, text=True).stdout.strip()


def git_init(ws: Path) -> str:
    _git(ws, "init", "-q")
    _git(ws, "config", "user.email", "rekurse@example.com")
    _git(ws, "config", "user.name", "rekurse")
    return commit_all(ws, "pristine")


def commit_all(ws: Path, msg: str) -> str:
    _git(ws, "add", "-A")
    subprocess.run(["git", "-C", str(ws), "commit", "-q", "-m", msg, "--allow-empty"],
                   check=True, capture_output=True, text=True)
    return _git(ws, "rev-parse", "HEAD")


def checkout(repo: Path, sha: str, dst: Path) -> Path:
    """Export `sha` from repo into a fresh, independent git repo at dst (no shared .git)."""
    dst.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", sha], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dst)], input=archive, check=True)
    git_init(dst)
    return dst


_PYTEST_CONFIGS = ("conftest.py", "pytest.ini", "setup.cfg", "tox.ini", "pyproject.toml")


def evaluate(ws: Path, trap: Trap) -> TestResult:
    """Restore the pristine tests, strip agent-added pytest config, run the suite."""
    shutil.rmtree(ws / "tests", ignore_errors=True)
    shutil.copytree(trap.pristine / "tests", ws / "tests")
    for name in _PYTEST_CONFIGS:
        p = ws / name
        if p.exists() and not (trap.pristine / name).exists():
            p.unlink()
    ini = ws / ".rekurse_pytest.ini"
    ini.write_text("[pytest]\n")
    env = {k: v for k, v in os.environ.items() if k not in ("DATE_TZ", "CURRENCY", "PYTEST_ADDOPTS")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", str(ini), "--rootdir", str(ws), "tests"],
        cwd=ws, env=env, capture_output=True, text=True, timeout=120,
    )
    ini.unlink(missing_ok=True)
    return TestResult(passed=proc.returncode == 0, output=proc.stdout + proc.stderr)


# ---------------------------------------------------------------- Pi sessions

def _read_entries(session_file: Path) -> list[dict]:
    return [json.loads(l) for l in session_file.read_text().splitlines() if l.strip()]


def user_turn_indices(entries: list[dict]) -> list[int]:
    """Indices (into the entry list) of user messages, in order."""
    return [i for i, e in enumerate(entries)
            if e.get("type") == "message" and e.get("message", {}).get("role") == "user"]


def assistant_text_after(entries: list[dict], user_idx: int) -> str:
    """Concatenated assistant text following the user entry at user_idx (for post-mortems)."""
    out = []
    for e in entries[user_idx + 1:]:
        if e.get("type") != "message":
            continue
        m = e["message"]
        if m.get("role") == "user":
            break
        if m.get("role") == "assistant":
            for c in m.get("content", []) or []:
                if isinstance(c, dict) and c.get("type") == "text":
                    out.append(c.get("text", ""))
    return "\n".join(out).strip()


def fork_before(session_file: Path, k: int, dst: Path, old_cwd: str, new_cwd: str) -> Path:
    """Copy the session up to (not including) user turn k, re-homed to new_cwd.

    k=0 yields a header-only session (fresh start with the same model settings).
    """
    entries = _read_entries(session_file)
    users = user_turn_indices(entries)
    cut = users[k] if k < len(users) else len(entries)
    kept = entries[:cut]
    header = dict(kept[0])
    header["id"] = str(uuid.uuid4())
    header["cwd"] = new_cwd
    kept[0] = header
    text = "\n".join(json.dumps(e) for e in kept) + "\n"
    text = text.replace(json.dumps(old_cwd)[1:-1], json.dumps(new_cwd)[1:-1])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)
    return dst


# ---------------------------------------------------------------- Pi driver

def assert_no_ancestor_context_files(ws: Path) -> None:
    """Pi loads AGENTS.md/CLAUDE.md from every ancestor of cwd; only the workspace's own file may exist."""
    for parent in ws.resolve().parents:
        for name in ("AGENTS.md", "CLAUDE.md"):
            if (parent / name).exists():
                raise RuntimeError(f"{parent / name} would leak into the agent under test; set REKURSE_WORK outside the repo")


def pi_command(session_file: Path, session_dir: Path, message: str, model: str, system_append: str = "") -> list[str]:
    """`system_append` is accepted for compatibility but unused: Pi ignores --append-system-prompt in -p mode,
    so lessons are injected through the workspace AGENTS.md instead (see models.agents_md)."""
    cmd = [*PI_BIN, "-p", "--mode", "json", "--session", str(session_file), "--session-dir", str(session_dir),
           "--model", model, "--thinking", "off", "--tools", PI_TOOLS,
           "--approve", "--no-extensions", "--no-skills"]
    # Pi prefers its own OAuth login over env vars; pass the API key explicitly so the run bills the key.
    key = {"anthropic": os.environ.get("ANTHROPIC_API_KEY"), "openai": os.environ.get("OPENAI_API_KEY")}.get(model.split("/")[0])
    if key:
        cmd += ["--api-key", key]
    return cmd + ["--", message]


def parse_pi_stdout(stdout: str) -> TurnResult:
    """A turn is ok only if the last assistant message stopped normally and the agent settled."""
    stop = None
    tokens = 0
    err = None
    settled = False
    texts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "agent_settled":
            settled = True
        elif t == "message_end":
            m = e.get("message", {})
            if m.get("role") == "assistant":
                stop = m.get("stopReason")
                err = m.get("errorMessage")
                tokens += (m.get("usage") or {}).get("totalTokens", 0) or 0
                for c in m.get("content", []) or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(c.get("text", ""))
    ok = settled and stop in ("stop", "toolUse")
    return TurnResult(ok=ok, stop_reason=stop, tokens=tokens or None, duration_s=0.0,
                      timed_out=False, error=err, assistant_text="\n".join(texts))


def _reader(stream, sink: list[str]):
    try:
        for line in stream:
            sink.append(line)
    except ValueError:
        pass


def run_turn(ws: Path, session_file: Path, session_dir: Path, message: str,
             system_append: str = "", model: str = AGENT_MODEL, timeout_s: int = TURN_TIMEOUT_S) -> TurnResult:
    """One non-interactive Pi turn in ws.

    Waits on the *process*, not the pipes: Pi spawns detached bash children that can keep stdout open
    after Pi exits. Readers run in daemon threads. On timeout: SIGTERM, then SIGKILL the process group.
    """
    import threading
    assert_no_ancestor_context_files(ws)
    session_dir.mkdir(parents=True, exist_ok=True)
    cmd = pi_command(session_file, session_dir, message, model, system_append)
    env = {k: v for k, v in os.environ.items() if k not in ("DATE_TZ", "CURRENCY")}
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=ws, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    out_lines: list[str] = []
    err_lines: list[str] = []
    for stream, sink in ((proc.stdout, out_lines), (proc.stderr, err_lines)):
        threading.Thread(target=_reader, args=(stream, sink), daemon=True).start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
                proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                continue
            except ProcessLookupError:
                break
    time.sleep(0.2)  # let readers drain what Pi wrote before exiting
    out, errtxt = "".join(out_lines), "".join(err_lines)
    res = parse_pi_stdout(out or "")
    res.duration_s = round(time.time() - t0, 1)
    res.timed_out = timed_out
    if timed_out:
        res.ok = False
        res.stop_reason = res.stop_reason or "timeout"
    if not res.ok and not res.error and errtxt:
        res.error = errtxt.strip()[-500:]
    return res
