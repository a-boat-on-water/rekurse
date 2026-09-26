# Rekurse — Project Plan (original brief)

> Original team brief, kept verbatim for context. The design we're actually building is [`docs/superpowers/specs/2026-09-26-rekurse-design.md`](superpowers/specs/2026-09-26-rekurse-design.md). Where they disagree, the spec wins.

> **Read this first.** This is the full brief for our MongoDB hackathon project. It is written for a reader (human or coding agent) with zero prior context. It covers what we're building, why, what's in and out of scope, the architecture, the build order, and the demo. The hard constraint: **the core code must be built in ~4 hours.**

---

## 0. TL;DR

**Rekurse finds the moment a coding agent went wrong, and proves which fix would have saved it.**

When a coding agent (we use **Pi**) spends hours going in circles before finally solving a problem, Rekurse:

1. **Replays** the session from earlier checkpoints, with the same code state and the same conversation up to that point.
2. **Tests candidate fixes** at each checkpoint. A fix is a lesson written into `AGENTS.md`, the agent's rules file.
3. **Measures** whether each fix makes the agent solve the problem, using a **hard metric** (the test suite passes), with repeated runs because agents are random.
4. **Adopts a lesson only if it's proven.** It must rescue the original session *and* help (or at least not hurt) a different held-out task.
5. **Writes a post-mortem**: where the session went wrong, which fix works, and the evidence.

Everything (sessions, checkpoints, lessons, runs, scores) is stored in **MongoDB Atlas**.

**Tagline:** *Never lose the same afternoon twice.*

---

## 1. The hackathon

- **Event:** MongoDB "Harness Engineering & Model Wrangling" Hackathon, NYC, Sat Sep 26 2026.
- **Finalists:** must **record a demo on-site today**. The top 3 present live at MongoDB.local NYC on Sep 30. There is $15k in prizes.
- **Must use:** MongoDB Atlas, plus ideally Vector Search and embeddings (Voyage AI).
- **Our problem statement: #1, "Recursive Harnessing."**
  > Build a self-improving agent harness that automatically evolves its own architecture: updating rules, context policies, guardrails, tool access, and more.
  - Rekurse updates the harness's **rules** (`AGENTS.md`), but only with evidence.
- **Judges, and what they'll care about:**
  - **Tenex** (Dan Zakon): context-as-code, harness engineering. Wants rigor.
  - **Vercel Compute** (Andrey Sibirev): infra, reliability, running lots of work in parallel.
  - **Radical Ventures** (Vin Sachidananda): "Is this a company?"
  - **OpenRouter** (Louis Vichy): working across many models.
  - **MongoDB** (Joseph Morais): creative, real use of Atlas and Vector Search.

---

## 2. The problem

Every engineer using coding agents knows this loop:

> You work with the agent for 2–3 hours. It goes in circles, making the same wrong assumption and patching the symptom instead of the cause. You get furious. Eventually *you* spot the real issue and it's fixed in minutes.

The worst part is that **nothing is learned**. Next week, the same class of mistake costs another afternoon.

Existing "self-learning" tools try to fix this, but they have two flaws:

1. **They learn from what you say, not from what happened.** They capture corrections like "no, use X" and write them to `CLAUDE.md`/`AGENTS.md`. A 3-hour loop often has no clean correction; the signal is that it *eventually got solved*.
2. **Nobody proves a lesson works.** Lessons get written based on an LLM's reflection. There's no test showing the lesson would actually have changed the outcome. So memory files bloat and rot.

---

## 3. What already exists (and the gap)

| Category | Examples | What they do | What they're missing |
|---|---|---|---|
| Lesson capture | claude-reflect, claude-soul, claude-memory | Detect corrections and write them to CLAUDE.md | No validation; learns from words, not outcomes |
| Self-learning harness | Letta Code (dreaming, skill learning) | Reviews sessions in the background and rewrites memory/skills | Admits overgeneralization and memory rot; lessons aren't proven |
| Research | ACE (evolving playbooks), GEPA (prompt evolution) | Evolve context/prompts from trajectories | ACE only appends and doesn't prune well; GEPA is expensive; neither targets real dev sessions |
| Replay / time travel | langgraph-replay, Agent VCR, Timewarp, AgentReplay, LangSmith, AgentOps | Fork and replay agent runs for debugging | Built for humans to look at; nothing feeds back into the agent's memory |

**Our gap:** nobody connects **replay** and **learning**. Rekurse is the first loop where a lesson only enters memory after a counterfactual replay proves it would have changed the outcome.

> Useful: Letta's open-source `@letta-ai/trajectory` package normalizes Claude Code/Codex sessions. It's a possible stretch goal for importing real sessions (see §6).

---

## 4. How Rekurse works (the core loop)

```
 ┌────────────────────┐
 │ 1. RECORD          │  Scripted "frustrated user" drives Pi on a trap repo.
 │    painful session │  Git commit + checkpoint saved at every user turn.
 └─────────┬──────────┘  Eventually a human hint solves it (like real life).
           ▼
 ┌────────────────────┐
 │ 2. REFLECT         │  LLM reads the whole session INCLUDING the solution and
 │    candidate       │  proposes 3 general lessons (no file names/line numbers).
 │    lessons         │
 └─────────┬──────────┘
           ▼
 ┌────────────────────┐
 │ 3. REPLAY SWEEP    │  For each checkpoint k × each lesson (+ a no-lesson baseline)
 │    counterfactuals │  × 3 seeds: restore code at k, fork the Pi session at k,
 │                    │  inject the lesson, continue WITHOUT the human hint.
 └─────────┬──────────┘  Success = test suite passes within a turn budget.
           ▼
 ┌────────────────────┐
 │ 4. VALIDATE        │  Best lesson is also run from scratch on a HELD-OUT trap
 │    (no overfit)    │  repo (same mistake class, different code). With vs without.
 └─────────┬──────────┘
           ▼
 ┌────────────────────┐
 │ 5. ADOPT + REPORT  │  Adopt only if: rescues the original AND helps (or at least
 │                    │  doesn't hurt) the held-out repo. Write AGENTS.md +
 └────────────────────┘  post-mortem + HTML report. All data in Atlas.
```

**The key output** is a timeline of the painful session where each checkpoint is colored by "rescue rate with lesson X vs. without." The **wrong turn** is the point where the baseline stops recovering on its own, and the proven lesson is what would have saved it.

---

## 5. Glossary

- **Pi:** a minimal open-source coding-agent harness (TypeScript, `@earendil-works/pi-coding-agent`). It stores sessions as JSONL **trees** (each entry has an `id` and `parentId`) and supports `/fork`, `/tree`, and `--fork <session>`. It reads `AGENTS.md` from the working directory.
- **Session:** one Pi conversation (a JSONL file).
- **Checkpoint:** a user turn in the session, plus the git commit of the code at that moment. It's the unit we replay from.
- **Trap repo:** a small project with a planted bug that reliably makes the agent patch the wrong place. It comes with a test that passes only when the *real* cause is fixed.
- **Held-out repo:** a second trap repo with the *same class* of mistake but different code. It's used to check that a lesson generalizes.
- **Lesson:** a short, general rule added to `AGENTS.md`, e.g. *"If a fix at the obvious location doesn't change the failing output, stop editing and trace where the input value originates."*
- **Replay / run:** one agent execution from a checkpoint with a given lesson (or none) and seed.
- **Rescue rate:** fraction of runs (out of 3) at a checkpoint that reach passing tests within the turn budget.
- **Baseline:** replay with no lesson. This is the control group.
- **Adopted / rejected / retired:** the lesson's status after validation.

---

## 6. Scope

### In scope (the 4-hour core)
1. **Trap repos:** one primary and one held-out, each with a test suite that defines success.
2. **Recorder:** drives Pi with scripted user turns, commits code at each turn, and saves the session and checkpoints to Mongo.
3. **Reflector:** an LLM proposes 3 candidate lessons from the full session and solution. Include a "generality check" that rejects lessons mentioning specific files, lines, or variable names.
4. **Replay runner:** restores code at checkpoint k, forks the Pi session at k, injects a lesson, continues with scripted user turns (no hint), runs tests, and records the result. Must run in parallel.
5. **Sweep + scoring:** checkpoints × (lessons + baseline) × 3 seeds, producing rescue rates.
6. **Validation:** best lesson, with vs. without, on the held-out repo from a fresh start.
7. **Adopt + outputs:** write the adopted lesson to `AGENTS.md`, plus a generated **post-mortem (markdown)** and a **static HTML report** (timeline, rescue-rate heatmap, before/after numbers).
8. **MongoDB:** all sessions, checkpoints, lessons, runs, and reports stored in Atlas. Use **Vector Search** to deduplicate lessons (a new candidate that's too similar to an existing lesson is merged, not added).

### Stretch goals (only after the core demo works end to end)
- **Bisect** instead of a linear sweep: fewer runs, and it matches the `git bisect` pitch.
- **Removal interventions:** test *deleting* a misleading message or context from the history, not just adding a rule.
- **Import real sessions:** use the Letta `trajectory` package to import real Claude Code sessions and produce an analysis-only post-mortem (no replay).
- **"Similar past struggles":** a vector search over checkpoint embeddings that finds past sessions like the current one.
- **Lesson retirement:** re-run the adopted lessons against all stored sessions and retire the ones that no longer help.

### Out of scope today
- Live, mid-session loop detection.
- Team or fleet sharing of lessons (mention it in the pitch as the vision).
- Supporting Claude Code as the replayed agent (its sessions can't be faithfully forked the way Pi's can).
- A real web app or auth. A static HTML report is enough.
- A hard fork of Pi's source code, unless strictly necessary (see §13).

---

## 7. Architecture

### Stack
- **Orchestrator:** Python 3.13, in this repo (`src/agent_memory_hackathon/`), managed with `uv`. Reuse the existing `db.py` (Atlas + vector helpers) and `embeddings.py` (Voyage/OpenAI).
- **Agent under test:** Pi, driven as a **subprocess** in non-interactive mode. **The first task is to verify Pi's non-interactive, JSON, or RPC modes** (`pi --help`) and how `--session` / `--fork` work from the CLI. Pick the simplest way to:
  - (a) send one user message and wait for the agent's turn to finish,
  - (b) continue an existing session, and
  - (c) fork a session at a specific entry or user message.
- **Lesson injection:** preferred method **A**: write the lesson into `AGENTS.md` in the replay workspace before starting the forked session. First verify that Pi rebuilds its system prompt from `AGENTS.md` in a new process. Fallback method **B**: prepend the lesson to the first replayed user message as `"Note from past experience: …"`. B always works; use it if A is uncertain.
- **Model:** a cheaper/faster model for the agent under test, which also makes it more likely to fall into the trap and keeps replays cheap. A stronger model for the reflector.
- **Isolation:** each replay runs in its own temp directory created with `git worktree add <tmp> <checkpoint_sha>` (or a plain copy), plus its own Pi session file. This is what makes runs parallel-safe.
- **Parallelism:** `asyncio` or a process pool with about 8–10 concurrent runs. **Turn budget:** about 15 agent turns or ~5 minutes per run, whichever comes first.

### Suggested modules
```
src/agent_memory_hackathon/
  db.py            # (exists) Atlas + vector helpers
  embeddings.py    # (exists)
  pi_driver.py     # run/continue/fork Pi sessions via CLI; parse JSONL
  recorder.py      # scripted-user recording of the painful session + git checkpoints
  reflector.py     # LLM → candidate lessons + generality check + vector dedupe
  replay.py        # one replay run: worktree @ sha, fork session, inject lesson, run, test
  sweep.py         # schedule checkpoints × lessons × seeds; parallel; write runs
  validate.py      # held-out with/without comparison; adopt/reject decision
  report.py        # post-mortem.md + report.html (timeline + heatmap)
  cli.py           # `rekurse record|reflect|sweep|validate|report|demo`
trap_repos/
  primary/         # planted-bug project + tests + scripted user turns + hint
  heldout/         # same mistake class, different code
```

### MongoDB collections (database: `rekurse`)
- `sessions`: `{_id, trap_repo, pi_session_path, model, started_at, solved_at_turn, total_turns}`
- `checkpoints`: `{_id, session_id, k, git_sha, pi_entry_id, user_msg, transcript_excerpt, embedding}`
- `lessons`: `{_id, text, type: "rule", status: "candidate"|"adopted"|"rejected"|"retired", source_session_id, embedding, scores: {...}}`
- `runs`: `{_id, session_id, checkpoint_k, lesson_id|null, seed, success, turns_used, tokens, duration_s, final_test_output}`
- `reports`: `{_id, session_id, wrong_turn_k, best_lesson_id, heldout: {with, without}, postmortem_md, created_at}`
- A vector index on `lessons.embedding` (for dedupe) and on `checkpoints.embedding` (for the stretch "similar struggles" search).

---

## 8. The demo scenario (trap repos)

We **stage** the painful session on a trap repo, so it's reproducible, cheap to replay, and has an objective pass/fail test. (The real-life story from Guy's own Claude Code sessions is the *pitch*; the trap repo is the *proof*.)

**Design rules for a good trap:**
- The failing test's error message points at the **wrong** place, the symptom.
- The real cause sits in a different module: a stale config, a cache file, a default loaded elsewhere.
- Patching the symptom location *looks* plausible but never makes the test pass, or it breaks another test.
- The fix is small once found.

**Example primary trap:** a date-formatting test is off by one day. The agent keeps editing `format_date()`. The real cause: `settings.py` loads the timezone from `config/defaults.json`, which overrides the environment variable.

**Example held-out trap:** a currency total is wrong. The agent keeps editing the rounding function. The real cause: the exchange rate comes from a stale `cache/rates.json`, loaded before the live value.

**The mistake class both share:** *patching the symptom instead of tracing where the input came from.* A lesson that fixes both is genuinely general.

**Scripted user turns** (in `trap_repos/<name>/script.yaml`):
- The opening task: "The test `test_format_date` is failing, please fix it."
- Frustrated follow-ups, repeated: "Still failing.", "That didn't fix it, try again.", "Tests still red."
- **The hint**, used only in the original recording after N turns (the moment the human "figures it out"): "I think the value is coming from somewhere else, check how settings are loaded."
- Replays **never** get the hint. Success in a replay means the lesson did the work.

**Sanity check before sweeping:** confirm the baseline (no lesson, no hint) **fails in most runs** from early checkpoints. If the trap is too easy, make it harder; if it's never solvable even with the hint, make it easier.

---

## 9. Build plan (4 hours)

Milestones are strict. **Don't start the next phase until the previous milestone passes.** Teammates can split the work by workstream.

| Time | Phase | Milestone (definition of done) |
|---|---|---|
| 0:00–0:30 | **Setup + spike** | `uv run smoke-test` passes. Pi's CLI modes verified; we can send a message, continue a session, and fork at an entry, all from Python. Trap repo v1 exists with a failing test. |
| 0:30–1:15 | **Record** | `rekurse record primary` produces a session and N checkpoints (with git shas) in Mongo; the session ends solved after the hint. |
| 1:15–2:00 | **Replay** | `rekurse replay --k 3 --lesson none --seed 1` restores code, forks, runs, tests, and writes a `runs` doc. Baseline fails most of the time. Lesson injection works. |
| 2:00–2:45 | **Reflect + sweep** | 3 candidate lessons generated and deduplicated; parallel sweep finishes; rescue-rate table printed. **At least one lesson clearly beats the baseline at some checkpoint.** |
| 2:45–3:20 | **Validate + adopt** | Held-out comparison with vs. without; adopt/reject logic; `AGENTS.md` updated; post-mortem written. |
| 3:20–4:00 | **Report + demo** | `report.html` (timeline heatmap, before/after, held-out result); `rekurse demo` runs the whole story; **demo video recorded on-site.** |

**Parallel workstreams (for multiple people/agents):**
- **A. Pi driver + replay:** `pi_driver.py`, `replay.py`. This is the critical path.
- **B. Trap repos + scripts:** `trap_repos/primary`, `trap_repos/heldout`, and tuning trap difficulty.
- **C. Mongo + reflector + scoring:** collections, vector index, `reflector.py`, `sweep.py` aggregation.
- **D. Report + pitch:** `report.py` (HTML), post-mortem template, demo script, slides.

**Run-budget math:** ~8 checkpoints × (3 lessons + 1 baseline) × 3 seeds = **96 runs**. At about 3 minutes each with 10 in parallel, that's roughly 30 minutes. Cut to fewer checkpoints (every other one) or 2 seeds if slow. **Precompute the sweep before the demo**; the live demo shows stored results plus one live replay.

---

## 10. Acceptance checks (what "working" means)

- [ ] The original session is recorded: it fails for N turns and is solved after the hint.
- [ ] The baseline replay (no lesson, no hint) from early checkpoints succeeds in **≤ 1 of 3** runs.
- [ ] The best lesson replay from the same checkpoints succeeds in **≥ 2 of 3** runs.
- [ ] The best lesson contains no repo-specific identifiers (passes the generality check).
- [ ] On the held-out repo, with the lesson beats without it (or at least ties). The adopt/reject decision is logged.
- [ ] Every session, checkpoint, lesson, run, and report is in Atlas; the lesson dedupe uses Vector Search.
- [ ] `report.html` shows the timeline heatmap, the wrong-turn checkpoint, before/after (turns and minutes), and the held-out result.
- [ ] A single command reproduces the demo from stored data.

---

## 11. Risks & fallbacks

| Risk | Fallback |
|---|---|
| Pi CLI can't fork at an arbitrary point non-interactively | Build the forked session ourselves: copy JSONL entries up to checkpoint k into a new session file (the format is plain JSONL with id/parentId), then continue it. Last resort: re-send the prefix messages as a single summarized context message. |
| AGENTS.md changes aren't picked up in a fork | Use injection method B (prepend the lesson to the replayed user message). |
| Trap too easy (baseline solves it) or too hard (nothing solves it) | Tune the trap: add or remove misleading clues; use a weaker or stronger agent model. |
| Replays too slow or too costly | Fewer checkpoints, 2 seeds, lower turn budget, cheaper model; precompute before the demo. |
| Randomness makes results noisy | Always show n/3 counts, never single runs; say "rescue rate" not "it works." |
| Running out of time | Cut in this order: HTML polish, then vector dedupe (keep a simple dedupe), then held-out validation (keep it in the pitch). **Never cut:** record, then replay, then sweep. |

---

## 12. Demo script & pitch (about 3 minutes)

1. **Hook (pain):** "Every engineer here has lost an afternoon to a coding agent going in circles, and then lost another afternoon to the *same* mistake next week. Tools that 'learn' write down lessons, but none of them can prove a lesson would actually have helped."
2. **Show the painful session:** the timeline, 20+ turns of circling, solved only after the human hint.
3. **Rewind:** "Rekurse went back to every point in this session and asked: *what one sentence would have saved it?*" Show the heatmap. The baseline stays red; with lesson X it turns green from checkpoint 3 onward. "Checkpoint 3 is the wrong turn."
4. **Proof, not vibes:** 0/3 without the lesson and 3/3 with it. Then the held-out repo, which the lesson never saw: still helps. "That's why it earned its place in AGENTS.md. Anything that fails this test never gets in."
5. **Live moment:** trigger one replay live from checkpoint 3 with the lesson and watch it pass.
6. **Vision:** "Aviation got safe because every crash is investigated and every lesson reaches the whole fleet. Agents crash a thousand times a day and nobody investigates. Rekurse is crash investigation for agents, and next it's every team's proven lessons, shared." Built on MongoDB: sessions, checkpoints, and lessons as documents, with Vector Search deduplicating lessons as memory grows.

**One-liners for Q&A:**
- *vs. Letta / claude-reflect:* "They write lessons. We prove them."
- *Why MongoDB:* "Checkpoints, runs, and lessons are all documents, and vector dedupe keeps memory from rotting."
- *Why Pi:* "Tree-structured sessions make forking at any point natural, and it's minimal enough to control."

---

## 13. Open decisions (defaults chosen; change if you disagree)

1. **"Fork off Pi"** is interpreted as *build on Pi and drive it as the agent under test*, **not** hard-forking its source code. We only patch Pi (or write a small Pi TypeScript extension) if the CLI can't do something we need.
2. **Demo session:** a staged trap repo, for reproducibility. Real Claude Code sessions are a stretch goal, used only for analysis.
3. **Intervention type:** `AGENTS.md` rules only. Removals, skills, and tool-permission changes are stretch goals.
4. **Language split:** Python orchestrator (existing repo); Pi stays TypeScript, used via its CLI.

---

## 14. Rules for the coding agent working on this repo

- **Verify before building.** First task: check `pi --help` and Pi's session docs, and write down the exact commands for send, continue, and fork in `AGENTS.md`. Don't assume flags exist.
- **Critical path first:** record, then replay, then sweep. Get one end-to-end replay working before anything else.
- **Keep it simple:** plain Python, subprocesses, `asyncio`. No frameworks we don't need.
- **Every run is isolated:** its own worktree and its own session file. Never mutate the original recording.
- **Log everything to Mongo** as you go. The report is generated from Mongo only.
- **Keep a small smoke test for each module** (e.g., `rekurse replay --dry-run`).
- **Update `AGENTS.md`** with decisions and discovered commands, so every teammate's agent shares the same context.
