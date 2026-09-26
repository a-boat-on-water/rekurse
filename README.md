# Rekurse

**Rekurse finds the turn where a coding agent went wrong, and proves which one-sentence rule would have saved it.**
_Never lose the same afternoon twice._ MongoDB Agentic Memory Hackathon, NYC, Sep 26 2026.

A scripted "frustrated user" drives the [Pi](https://github.com/earendil-works/pi-coding-agent) coding agent on a
trap repo until a human hint rescues it. Rekurse then forks the recorded session at every checkpoint, replays it
with and without a candidate lesson, finds the first checkpoint the agent can no longer recover from, and only
writes a lesson into `AGENTS.md` if it rescues the agent there **and** on a held-out trap it has never seen.
Every session, checkpoint, run and lesson lives in MongoDB Atlas; Vector Search dedupes lessons.

```bash
uv run rekurse demo --fake --heldout heldout   # whole loop offline in ~10 s (fake agent, in-memory store)
uv run rekurse demo --live --heldout heldout   # real Pi + Atlas + Voyage + Claude reflector (~20 min)
uv run rekurse demo                            # rebuild out/ from the latest report in Atlas
```
Outputs: `out/report.html` (rescue grid), `out/postmortem.md`, `out/AGENTS.md` (proven lessons block).

## How we know it works

`uv run pytest` runs offline in under 10 seconds, no LLM, no network:

- **Trap fairness** (`tests/test_traps.py`): the pristine trap fails, the known real fix passes, the obvious
  symptom patch still fails. For both traps.
- **Anti-cheat**: an agent that edits the tests, adds a `conftest.py`, or drops a `pytest.ini` gets no credit.
  `evaluate()` restores the hidden tests before every check.
- **Harness** (`tests/test_harness.py`): session forking rewrites the working directory and truncates before the
  right user turn (against a real Pi session file); Pi's JSON output is judged by stop reason, not exit code.
- **Pure logic** (`tests/test_pure.py`): bisect over checkpoints, early-stopping cells, rescue rate excluding timeouts,
  one-sided Fisher exact test, adopt/reject rules, and the generality filter that rejects lessons naming trap identifiers.
- **End to end** (`tests/test_e2e.py`): the full record → sweep → reflect → dedupe → lessons → held-out → decide →
  report loop on a fake Pi and in-memory store. Asserts the wrong turn is found, a lesson naming `format_date` is
  rejected, a near-duplicate is merged by cosine similarity, and the surviving lesson is adopted.

Honesty rules baked into the numbers: the decision uses **fresh** baseline runs at the wrong turn (not the sweep
runs that defined it), n=5 per decision cell, timed-out runs are excluded rather than counted as failures, the
baseline gets a placebo AGENTS.md line of similar length, and every probed cell is shown in the grid (unprobed cells
are gray: the wrong turn is bisected, and a cell stops after 2 seeds when 0/2 or 2/2 already decides it).


## Setup (5 min)

Needs Python via [uv](https://docs.astral.sh/uv/) (`brew install uv`) and Git.

```bash
git clone <repo>
cd rekurse
uv sync                    # creates .venv with Python 3.13 + deps
cp .env.example .env       # then fill in MONGODB_URI and your API keys
uv run smoke-test          # Atlas + embeddings + vector search + LLM check
```

`smoke-test` should end with **All good ✅**. If Atlas times out, check that your IP is allowed
(Atlas → Network Access; for the venue, `0.0.0.0/0` is simplest for the day).

## Coding agents

- **Pi**: `npm install -g @earendil-works/pi-coding-agent`, then run `pi` in the repo and `/login`.
- **Claude Code**: run `claude` in the repo.

Both read `AGENTS.md` (`CLAUDE.md` links to it) for project context and rules — update it once the idea is picked.

## Layout

```
src/rekurse/
  models.py     dataclasses, config constants, load_trap()
  harness.py    Pi subprocess + JSON parser, session fork, git checkout, evaluate() with anti-cheat
  pipeline.py   record, replay, sweep, find_wrong_turn, fisher_p, decide, reflector + generality + dedupe
  store.py      MemoryStore (tests) and MongoStore (Atlas, Vector Search)
  report.py     report.html, postmortem.md, AGENTS.md block
  demo.py       CLI + orchestrator
  db.py, embeddings.py, smoke_test.py
trap_repos/{primary,heldout}/{trap.json,pristine/,solution/,symptom/}
tests/          fake_pi.py + test_*.py + fixtures/
```
