"""Record, replay, sweep, bisect, reflect, dedupe, decide. Pure functions stay pure."""
from __future__ import annotations

import ast
import json
import math
import re
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from . import harness
from .models import (AGENT_MODEL, CONCURRENCY, DEDUPE_THRESHOLD, REFLECTOR_MODEL, REPLAY_MAX_TURNS,
                     Checkpoint, Decision, ReplaySpec, RunResult, Trap, agents_md)

_now = lambda: datetime.now(timezone.utc).isoformat()

# ------------------------------------------------------------------ record

def record(trap: Trap, store, run_group: str, work_root: Path, log=print) -> dict:
    """Drive Pi with the scripted frustrated user. Returns the session doc (see .accepted)."""
    sid = uuid.uuid4().hex[:8]
    work = work_root / sid
    repo, sessions = work / "repo", work / "sessions"
    harness.materialize_trap(trap, repo)
    harness.git_init(repo)
    session_file = sessions / "record.jsonl"
    checkpoints: list[Checkpoint] = []
    solved_turn = None
    hint_turn = trap.hint_after
    for k in range(trap.max_turns):
        sha = harness.commit_all(repo, f"before turn {k}")
        if k == 0:
            msg = trap.opening
        elif k == hint_turn:
            msg = trap.hint
        else:
            msg = trap.followups[(k - 1) % len(trap.followups)]
        cp = Checkpoint(session_id=sid, k=k, git_sha=sha, user_msg=msg, is_hint=(k == hint_turn))
        log(f"  record turn {k}: {msg!r}")
        r = harness.run_turn(repo, session_file, sessions / "sd", msg)
        if not r.ok:
            log(f"  turn {k} did not complete: {r.stop_reason}{' (timed out)' if r.timed_out else ''} {r.error or ''}")
        cp.agent_msg_excerpt = (r.assistant_text or "")[:600]
        checkpoints.append(cp)
        if harness.evaluate(repo, trap).passed:
            solved_turn = k
            log(f"  solved at turn {k}")
            break
    final_sha = harness.commit_all(repo, "final")
    failed_before_hint = solved_turn is None or solved_turn >= hint_turn
    accepted = solved_turn is not None and failed_before_hint and hint_turn >= 3 and solved_turn - hint_turn < 3
    doc = {
        "_id": sid, "run_group": run_group, "trap": trap.name, "work_dir": str(work), "repo": str(repo),
        "session_file": str(session_file), "agent_model": AGENT_MODEL, "hint_turn": hint_turn,
        "solved_turn": solved_turn, "total_turns": len(checkpoints), "final_sha": final_sha,
        "accepted": accepted, "created_at": _now(),
    }
    store.save_session(doc)
    store.save_checkpoints([{"_id": c._id, **c.__dict__} for c in checkpoints])
    return doc


# ------------------------------------------------------------------ replay

def replay_one(spec: ReplaySpec, trap: Trap, store, work_root: Path, session_doc: dict | None = None,
               checkpoints: list[dict] | None = None, keep: bool = False) -> RunResult:
    tmp = work_root / "runs" / spec.run_id.replace(":", "_")
    shutil.rmtree(tmp, ignore_errors=True)
    ws, session_file, sd = tmp / "ws", tmp / "session.jsonl", tmp / "sd"
    if spec.session_id is None:
        harness.materialize_trap(trap, ws)
        harness.git_init(ws)
        first_msg = trap.opening
    else:
        cp = next(c for c in checkpoints if c["k"] == spec.checkpoint_k)
        harness.checkout(Path(session_doc["repo"]), cp["git_sha"], ws)
        harness.fork_before(Path(session_doc["session_file"]), spec.checkpoint_k, session_file,
                            old_cwd=session_doc["repo"], new_cwd=str(ws))
        first_msg = cp["user_msg"]
    # Injection: the lesson (or a placebo for the baseline arm) is a line in the workspace's AGENTS.md, which Pi
    # loads into its system prompt on every turn. Same mechanism the adopted lesson uses in real life.
    (ws / "AGENTS.md").write_text(agents_md(spec.lesson_text))
    messages = [first_msg] + [f for f in trap.followups if f != trap.hint]
    t0 = time.time()
    success, turns, tokens, stop, timed_out, out = False, 0, 0, None, False, ""
    for msg in messages[:REPLAY_MAX_TURNS]:
        r = harness.run_turn(ws, session_file, sd, msg)
        turns += 1
        tokens += r.tokens or 0
        stop, timed_out = r.stop_reason, r.timed_out
        if not r.ok:
            out = r.error or ""
            break
        res = harness.evaluate(ws, trap)
        out = res.output
        if res.passed:
            success = True
            break
    result = RunResult(spec=spec, success=success, turns_used=turns, duration_s=round(time.time() - t0, 1),
                       tokens=tokens or None, stop_reason=stop, timed_out=timed_out, final_test_output=out)
    doc = result.to_doc()
    doc["created_at"] = _now()
    store.save_run(doc)
    if not keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def run_many(specs: Iterable[ReplaySpec], fn: Callable[[ReplaySpec], RunResult],
             concurrency: int = CONCURRENCY, log=print) -> list[RunResult]:
    specs = list(specs)
    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        for r in ex.map(fn, specs):
            log(f"  {r.spec.purpose} k={r.spec.checkpoint_k} lesson={r.spec.lesson_id or 'base'} "
                f"seed={r.spec.seed}: {'PASS' if r.success else 'fail'}"
                f"{'' if r.counted else ' (not counted: ' + str(r.stop_reason) + ')'}")
            results.append(r)
    return results


# ------------------------------------------------------------------ statistics (pure)

def rescue_rate(runs: Iterable) -> tuple[int, int]:
    """(successes, counted). Accepts RunResult objects or run docs. Timed-out/error runs are excluded."""
    s = n = 0
    for r in runs:
        if isinstance(r, RunResult):
            counted, success = r.counted, r.success
        else:
            counted = not r.get("timed_out") and r.get("stop_reason") not in ("error", "aborted")
            success = r.get("success", False)
        if counted:
            n += 1
            s += int(bool(success))
    return s, n


def find_wrong_turn(rates: dict[int, tuple[int, int]], max_rate: float = 1 / 3) -> int | None:
    """First checkpoint (ascending k) whose baseline rescue rate is <= max_rate. None if none qualifies.

    Non-monotone inputs return the first failing k; the report shows every probed cell so the claim stays honest.
    """
    for k in sorted(rates):
        s, n = rates[k]
        if n and s / n <= max_rate:
            return k
    return None


def fisher_p(a_succ: int, a_n: int, b_succ: int, b_n: int) -> float:
    """One-sided Fisher exact p-value that group A's success rate exceeds group B's."""
    total_succ, total = a_succ + b_succ, a_n + b_n
    if total == 0:
        return 1.0
    denom = math.comb(total, a_n)
    p = 0.0
    for x in range(a_succ, min(a_n, total_succ) + 1):
        if total_succ - x <= b_n:
            p += math.comb(total_succ, x) * math.comb(total - total_succ, a_n - x) / denom
    return min(1.0, p)


def decide(lesson: tuple[int, int], baseline: tuple[int, int],
           heldout_with: tuple[int, int] | None, heldout_without: tuple[int, int] | None,
           lesson_min: float = 0.8, baseline_max: float = 0.2) -> Decision:
    d = Decision(adopted=True)
    ls, ln = lesson
    bs, bn = baseline
    if not ln or ls / ln < lesson_min:
        d.failed_conditions.append(f"lesson rescue {ls}/{ln} below {lesson_min:.0%}")
    if not bn or bs / bn > baseline_max:
        d.failed_conditions.append(f"baseline rescue {bs}/{bn} above {baseline_max:.0%}")
    if heldout_with is None or heldout_without is None:
        d.notes.append("held-out not evaluated")
    else:
        hs, hn = heldout_with
        ws_, wn = heldout_without
        if hn and wn and hs / hn < ws_ / wn:
            d.failed_conditions.append(f"held-out with lesson {hs}/{hn} below without {ws_}/{wn}")
    d.adopted = not d.failed_conditions
    return d


# ------------------------------------------------------------------ reflector

_STOP = {"settings", "config", "configuration", "default", "defaults", "value", "values", "test", "tests",
         "app", "date", "dates", "format", "load", "loads", "loaded", "env", "environment", "time", "zone",
         "key", "keys", "path", "file", "files", "local", "total", "totals", "rate", "rates", "cache", "cached",
         "invoice", "round", "rounding", "currency", "timezone", "helper", "helpers", "main", "run", "data"}


def trap_identifiers(trap: Trap) -> set[str]:
    ids: set[str] = set()
    for p in trap.pristine.rglob("*"):
        if p.is_dir() or "tests" in p.relative_to(trap.pristine).parts:
            continue
        ids.add(p.stem.lower())
        if p.suffix == ".py":
            try:
                tree = ast.parse(p.read_text())
            except SyntaxError:
                continue
            # Only names the trap *defines* (functions, classes, assigned names, parameters), not stdlib it references.
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    ids.add(node.name.lower())
                elif isinstance(node, ast.arg):
                    ids.add(node.arg.lower())
                elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in targets:
                        for n in ast.walk(t):
                            if isinstance(n, ast.Name):
                                ids.add(n.id.lower())
        elif p.suffix == ".json":
            try:
                def keys(o):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            ids.add(str(k).lower()); keys(v)
                    elif isinstance(o, list):
                        for v in o: keys(v)
                keys(json.loads(p.read_text()))
            except json.JSONDecodeError:
                pass
    return {i for i in ids if len(i) > 2 and i not in _STOP and not i.startswith("_")}


def is_general(text: str, identifiers: set[str], max_words: int = 30) -> tuple[bool, str | None]:
    if len(text.split()) > max_words:
        return False, f"too long ({len(text.split())} words)"
    if re.search(r"(^|\s)(\.{0,2}/|~/)[\w./-]+|\b[\w.-]+/[\w.-]+\.\w{1,5}\b|\\\\", text):
        return False, "contains a path"
    if re.search(r"\b\w+\.(py|json|yaml|yml|toml|ini|cfg|txt|md)\b", text, re.I):
        return False, "names a file"
    if re.search(r"\b[a-zA-Z_]\w*\.[a-zA-Z_]\w*\(", text):
        return False, "names a function"
    words = {w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)}
    hit = sorted(words & identifiers)
    if hit:
        return False, f"names trap identifier: {', '.join(hit[:3])}"
    return True, None


REFLECT_PROMPT = """You are reviewing a coding agent's session that went badly. The agent kept patching the symptom.
Below is the transcript up to the point where a human stepped in, followed by the diff of the fix that finally worked.

Propose exactly 3 short, general rules (one sentence each, under 25 words) that would have led the agent to find
this fix on its own. Constraints:
- The agent can only read and edit files. It cannot run commands, tests, or scripts, so rules must not ask it to
  reproduce, print, log, or execute anything.
- Each rule must be actionable from the agent's very first response, before it has received any feedback. Rules
  that only fire after "repeated failures" are useless here.
- The user's first message pointed at the wrong place. Good rules say what to verify, and where to look, before
  trusting a reported location and editing it.
- General engineering practice only: no file names, function names, variable names, line numbers, or
  project-specific words.
Output one rule per line, no numbering, nothing else.

TRANSCRIPT
{transcript}

FIX DIFF
{diff}
"""


def transcript_before_hint(session_doc: dict, checkpoints: list[dict]) -> str:
    entries = harness._read_entries(Path(session_doc["session_file"]))
    users = harness.user_turn_indices(entries)
    parts = []
    for cp in checkpoints:
        if cp["is_hint"]:
            break
        k = cp["k"]
        parts.append(f"USER: {cp['user_msg']}")
        if k < len(users):
            parts.append(f"AGENT: {harness.assistant_text_after(entries, users[k])[:800]}")
    return "\n".join(parts)


def fix_diff(session_doc: dict, checkpoints: list[dict]) -> str:
    hint_cp = next((c for c in checkpoints if c["is_hint"]), checkpoints[-1])
    out = subprocess.run(["git", "-C", session_doc["repo"], "diff", hint_cp["git_sha"], session_doc["final_sha"],
                          "--", ".", ":(exclude)tests"], capture_output=True, text=True)
    return out.stdout[:6000]


def propose_lessons_llm(transcript: str, diff: str, model: str = REFLECTOR_MODEL) -> list[str]:
    import os
    prompt = REFLECT_PROMPT.format(transcript=transcript, diff=diff)
    if model.startswith("claude"):
        import anthropic
        msg = anthropic.Anthropic().messages.create(model=model, max_tokens=400,
                                                    messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text
    else:
        from openai import OpenAI
        resp = OpenAI().chat.completions.create(model=model, max_completion_tokens=400,
                                                messages=[{"role": "user", "content": prompt}])
        text = resp.choices[0].message.content or ""
    lines = [re.sub(r"^[\s\-\*\d\.\)]+", "", l).strip() for l in text.splitlines()]
    return [l for l in lines if len(l) > 10][:3]


def reflect(candidates: list[str], trap: Trap, store, run_group: str, session_id: str,
            embed: Callable[[list[str]], list[list[float]]], threshold: float = DEDUPE_THRESHOLD, log=print) -> list[dict]:
    """Generality check, then vector dedupe against everything already in `lessons`. Returns surviving lesson docs."""
    from .store import cosine
    ids = trap_identifiers(trap)
    survivors: list[dict] = []
    texts = [c.strip() for c in candidates if c.strip()]
    embeddings = embed(texts) if texts else []
    for text, emb in zip(texts, embeddings):
        ok, reason = is_general(text, ids)
        lid = uuid.uuid4().hex[:8]
        base = {"_id": lid, "run_group": run_group, "text": text, "source_session_ids": [session_id],
                "seen_count": 1, "embedding": emb, "created_at": _now(), "scores": {}}
        if not ok:
            store.save_lesson({**base, "status": "rejected", "reason": f"not_general: {reason}", "top1_similarity": None})
            log(f"  lesson rejected ({reason}): {text}")
            continue
        # Atlas indexes new docs with a lag of seconds, so also compare against this batch's survivors locally.
        top = store.similar_lessons(emb, k=1)
        top = top[0] if top else None
        for prev in survivors:
            c = cosine(emb, prev["embedding"])
            if top is None or c > top["score"]:
                top = dict(prev, score=c)
        top_score = top["score"] if top else None
        if top and top_score >= threshold:
            store.update_lesson(top["_id"], {"seen_count": top.get("seen_count", 1) + 1,
                                             "source_session_ids": sorted(set(top.get("source_session_ids", [])) | {session_id})})
            store.save_lesson({**base, "status": "merged", "reason": f"duplicate of {top['_id']}",
                               "merged_into": top["_id"], "top1_similarity": round(top_score, 3)})
            log(f"  lesson merged into {top['_id']} (cos {top_score:.3f}): {text}")
            if top.get("status") in ("candidate", "adopted") and top["run_group"] == run_group and top not in survivors:
                pass
            continue
        doc = {**base, "status": "candidate", "reason": None, "top1_similarity": round(top_score, 3) if top_score is not None else None}
        store.save_lesson(doc)
        survivors.append(doc)
        log(f"  lesson candidate (top1 cos {top_score if top_score is None else round(top_score, 3)}): {text}")
    return survivors
