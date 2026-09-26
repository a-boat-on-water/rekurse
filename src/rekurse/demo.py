"""CLI: `rekurse demo [--live|--fake]` and `rekurse replay`. The orchestrator lives here too."""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import harness, pipeline, report
from .models import (CONCURRENCY, DECISION_SEEDS, OUT_DIR, ROOT, SEEDS, ReplaySpec, load_trap)
from .store import MemoryStore

_now = lambda: datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ offline stand-ins

def fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic bag-of-words hashing; near-identical sentences get high cosine."""
    out = []
    for t in texts:
        v = [0.0] * 256
        for w in re.findall(r"[a-z]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


def stub_reflector(transcript: str, diff: str) -> list[str]:
    return [
        "When a test fails on a computed value, trace where the value comes from before patching the function that produces it.",
        "Fix format_date so it respects the configured timezone.",
        "Before patching the function, trace where the value comes from when a test fails on a computed value.",
    ]


# ------------------------------------------------------------------ orchestrator

def run_pipeline(store, trap_name: str, heldout_name: str | None, run_group: str, work_root: Path,
                 reflector, embed, seeds: int = SEEDS, decision_seeds: int = DECISION_SEEDS,
                 concurrency: int = CONCURRENCY, log=print) -> dict:
    trap = load_trap(trap_name)
    work_root.mkdir(parents=True, exist_ok=True)

    log(f"== record ({trap.name})")
    session = pipeline.record(trap, store, run_group, work_root, log=log)
    if not session["accepted"]:
        log("  recording not accepted (must fail before the hint and pass shortly after); re-recording once")
        session = pipeline.record(trap, store, run_group, work_root, log=log)
    cps = store.get_checkpoints(session["_id"])
    pre_hint = [c["k"] for c in cps if not c["is_hint"] and c["k"] < session["hint_turn"]]

    def replay(spec):
        return pipeline.replay_one(spec, load_trap(spec.trap), store, work_root, session, cps)

    log(f"== sweep: baseline x{seeds} at checkpoints {pre_hint}")
    sweep = pipeline.run_many(
        [ReplaySpec(run_group, trap.name, session["_id"], k, None, None, s, "sweep") for k in pre_hint for s in range(1, seeds + 1)],
        replay, concurrency, log)
    rates = {k: pipeline.rescue_rate(r for r in sweep if r.spec.checkpoint_k == k) for k in pre_hint}
    wt = pipeline.find_wrong_turn(rates)
    notes = []
    if wt is None:
        wt = pre_hint[-1]
        notes.append("baseline recovered from every probed checkpoint; testing lessons at the last pre-hint turn")
    log(f"  sweep rates {rates}; wrong turn = {wt}")

    log("== reflect")
    transcript = pipeline.transcript_before_hint(session, cps)
    diff = pipeline.fix_diff(session, cps)
    candidates = reflector(transcript, diff)
    lessons = pipeline.reflect(candidates, trap, store, run_group, session["_id"], embed, log=log)

    lesson_rates, best = {}, None
    decision_l, decision_b = (0, 0), (0, 0)
    if lessons:
        log(f"== lessons x{seeds} at wrong turn {wt}")
        lr = pipeline.run_many(
            [ReplaySpec(run_group, trap.name, session["_id"], wt, L["_id"], L["text"], s, "lesson") for L in lessons for s in range(1, seeds + 1)],
            replay, concurrency, log)
        for L in lessons:
            mine = [r for r in lr if r.spec.lesson_id == L["_id"]]
            lesson_rates[L["_id"]] = pipeline.rescue_rate(mine)
        def key(L):
            s, n = lesson_rates[L["_id"]]
            turns = sum(r.turns_used for r in lr if r.spec.lesson_id == L["_id"] and r.success)
            return (s / n if n else 0, -turns)
        best = max(lessons, key=key)
        log(f"== decision: best lesson {best['_id']} top-up to {decision_seeds} + fresh baseline x{decision_seeds} at {wt}")
        extra = list(range(seeds + 1, decision_seeds + 1))
        dec = pipeline.run_many(
            [ReplaySpec(run_group, trap.name, session["_id"], wt, best["_id"], best["text"], s, "decision") for s in extra] +
            [ReplaySpec(run_group, trap.name, session["_id"], wt, None, None, 100 + s, "decision") for s in range(1, decision_seeds + 1)],
            replay, concurrency, log)
        decision_l = pipeline.rescue_rate([r for r in lr if r.spec.lesson_id == best["_id"]] + [r for r in dec if r.spec.lesson_id])
        decision_b = pipeline.rescue_rate(r for r in dec if r.spec.lesson_id is None)

    hw = hwo = None
    if best and heldout_name:
        log(f"== held-out ({heldout_name}): lesson vs placebo, fresh start x{seeds}")
        ho = load_trap(heldout_name)
        hr = pipeline.run_many(
            [ReplaySpec(run_group, ho.name, None, 0, best["_id"], best["text"], s, "heldout") for s in range(1, seeds + 1)] +
            [ReplaySpec(run_group, ho.name, None, 0, None, None, s, "heldout") for s in range(1, seeds + 1)],
            lambda sp: pipeline.replay_one(sp, ho, store, work_root), concurrency, log)
        hw = pipeline.rescue_rate(r for r in hr if r.spec.lesson_id)
        hwo = pipeline.rescue_rate(r for r in hr if r.spec.lesson_id is None)

    d = pipeline.decide(decision_l, decision_b, hw, hwo) if best else pipeline.Decision(False, ["no lesson survived the generality check"])
    notes += d.notes
    if best:
        for L in lessons:
            status = "adopted" if (L["_id"] == best["_id"] and d.adopted) else ("rejected" if L["_id"] == best["_id"] else "candidate")
            reason = None if status != "rejected" else "; ".join(d.failed_conditions)
            store.update_lesson(L["_id"], {"status": status, "reason": reason, "scores": {
                "wrong_turn": list(lesson_rates[L["_id"]]),
                "decision": list(decision_l) if L["_id"] == best["_id"] else None,
                "heldout_with": list(hw) if hw and L["_id"] == best["_id"] else None,
                "heldout_without": list(hwo) if hwo and L["_id"] == best["_id"] else None,
                "computed_from_run_group": run_group}})
    doc = {
        "_id": run_group, "run_group": run_group, "session_id": session["_id"], "trap": trap.name, "heldout": heldout_name,
        "wrong_turn_k": wt, "probed_ks": pre_hint, "sweep_rates": {str(k): list(v) for k, v in rates.items()},
        "lesson_rates": {k: list(v) for k, v in lesson_rates.items()}, "best_lesson_id": best["_id"] if best else None,
        "decision_lesson": list(decision_l), "decision_baseline": list(decision_b),
        "heldout_with": list(hw) if hw else None, "heldout_without": list(hwo) if hwo else None,
        "decision": "adopted" if d.adopted else "rejected", "failed_conditions": d.failed_conditions, "notes": notes,
        "p_values": {"wrong_turn": pipeline.fisher_p(*decision_l, *decision_b),
                     "heldout": pipeline.fisher_p(*hw, *hwo) if hw and hwo else None},
        "created_at": _now(),
    }
    doc["postmortem_md"] = report.postmortem(store, doc)
    store.save_report(doc)
    log(f"== {doc['decision'].upper()} {d.failed_conditions or ''}")
    return doc


# ------------------------------------------------------------------ CLI

def _fake_mode():
    harness.PI_BIN[:] = [sys.executable, str(ROOT / "tests" / "fake_pi.py")]
    os.environ.setdefault("REKURSE_FAKE_RECOVER_BEFORE", "2")


def _mongo_store():
    from .embeddings import dims
    from .store import MongoStore
    store = MongoStore()
    store.ensure_indexes(dims())
    return store


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rekurse")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the pipeline (--live / --fake) or rebuild out/ from Atlas")
    d.add_argument("--live", action="store_true"); d.add_argument("--fake", action="store_true")
    d.add_argument("--trap", default="primary"); d.add_argument("--heldout", default=None)
    d.add_argument("--run-group", default=None); d.add_argument("--out", default=str(OUT_DIR))
    r = sub.add_parser("replay", help="one replay against real Pi (spike)")
    r.add_argument("--trap", default="primary"); r.add_argument("--k", type=int, default=0)
    r.add_argument("--lesson", default="none"); r.add_argument("--seed", type=int, default=1)
    r.add_argument("--session", default=None); r.add_argument("--fake", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out) if hasattr(a, "out") else OUT_DIR

    if a.cmd == "replay":
        if a.fake: _fake_mode()
        store = MemoryStore() if a.fake else _mongo_store()
        trap = load_trap(a.trap)
        session = store.get_session(a.session) if a.session else None
        cps = store.get_checkpoints(a.session) if a.session else None
        spec = ReplaySpec("spike", trap.name, a.session, a.k, None if a.lesson == "none" else "manual",
                          None if a.lesson == "none" else a.lesson, a.seed, "spike")
        res = pipeline.replay_one(spec, trap, store, out / "work", session, cps, keep=True)
        print(res.to_doc())
        return

    if a.fake:
        _fake_mode()
        store = MemoryStore()
        rg = a.run_group or f"fake-{uuid.uuid4().hex[:6]}"
        doc = run_pipeline(store, a.trap, a.heldout, rg, out / "work", stub_reflector, fake_embed)
    elif a.live:
        from .embeddings import embed
        store = _mongo_store()
        rg = a.run_group or f"live-{datetime.now().strftime('%m%d-%H%M')}"
        doc = run_pipeline(store, a.trap, a.heldout, rg, out / "work", pipeline.propose_lessons_llm, embed)
    else:
        store = _mongo_store()
        doc = store.get_report(a.run_group) if a.run_group else store.latest_report()
        if not doc:
            sys.exit("no report in Atlas yet; run `rekurse demo --live` first")
    paths = report.write_outputs(store, doc, out)
    print("\n".join(str(p) for p in paths))


if __name__ == "__main__":
    main()
