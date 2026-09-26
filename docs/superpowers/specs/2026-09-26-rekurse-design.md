# Rekurse: Design Spec

**Date:** 2026-09-26 (hackathon day)
**Status:** Draft for team review
**Source brief:** [`docs/brief.md`](../../brief.md)
**Build budget:** about 4 hours, 2 to 4 people

> **Rekurse finds the turn where a coding agent went wrong, and proves which one-sentence rule would have saved it.**
> Tagline: *Never lose the same afternoon twice.*

---

## 1. What we agreed

**What you said:**
- Build the "Never lose the same afternoon twice" story. Features: bisect to the wrong turn, a validated fix, and an auto post-mortem.
- Fork off Pi. Keep it simple.
- A few pieces done well beat lots of features.
- Testing must prove it works. Judges will look at the code.
- The presentation is a **1 minute video**.
- Split the work between 2 and 4 people.

**What I assumed (push back if wrong):**
- "Fork Pi" means we build on Pi and use its session forking (`--fork`, JSONL tree). We do **not** patch Pi's source unless the spike (Phase 0) proves the CLI can't do something. See §11.
- The painful session is **staged** on a trap repo so it's reproducible and has an objective pass/fail test. The real-life story is the pitch, not the evidence.
- The only intervention type is an `AGENTS.md` rule. No removals, skills, or tool changes.
- We **bisect** to find the wrong turn instead of sweeping every checkpoint. It's cheaper, it matches the pitch, and it gives us fewer runs to babysit.

**Success means:**
1. One command (`rekurse demo`) regenerates the whole story from Atlas.
2. At the wrong turn, the baseline rescues **≤ 1/3** runs and the adopted lesson rescues **≥ 2/3**.
3. On a held-out trap the lesson has never seen, with-lesson **≥** without-lesson.
4. `uv run pytest` passes with no network and no LLM (fake Pi + in-memory store), so judges can verify the logic in 10 seconds.
5. A 60 second video that a judge can follow with no narration context.

---

## 2. Cut list (what we are NOT building)

Everything below is out of scope today. If someone finishes early, they polish the demo; they don't add features.

- Linear full sweep over all checkpoints (bisect replaces it; a `--linear` flag exists only if bisect gets done early and there's budget).
- Removal interventions, skills, tool-permission changes.
- Importing real Claude Code sessions (Letta `trajectory`).
- "Similar past struggles" search over checkpoints.
- Lesson retirement.
- Live mid-session loop detection.
- A web app. The report is one static HTML file.
- Multi-model comparisons (mentioned in the pitch for OpenRouter; agent model is just a config value).

What **stays**, because the judges care: Atlas as the only source of truth for the report, and Vector Search for lesson dedupe (MongoDB judge). Tests plus a harness that can't be gamed (Tenex judge, and the "they'll check the code" constraint). Parallel runs (Vercel judge).

---

## 3. The loop

```
record ──> reflect ──> bisect ──> test lessons ──> validate ──> adopt + report
  │          │           │            │               │              │
  Pi +     3 general   find the     each lesson     best lesson    AGENTS.md,
  scripted  rules from  wrong turn   × 3 seeds at    on held-out    post-mortem.md,
  user +    the full    using        the wrong turn  trap, fresh    report.html
  git sha   session     baseline     (parallel)      start, with    (all from Atlas)
  per turn  + fix       replays                      vs without
```

### 3.1 Record
A scripted "frustrated user" drives Pi on the primary trap repo. Before each user turn the harness commits the workspace and stores a **checkpoint** `{k, git_sha, pi_entry_id, user_msg}`. After `hint_after` turns the script sends the hint. Recording stops when the hidden test suite passes, or at `max_turns`.

**Recording is accepted only if** it failed for at least 3 turns before the hint and passed within 3 turns after it. Otherwise we re-record (the agent is random) or tune the trap.

### 3.2 Reflect
One call to the reflector model (`claude-sonnet-5`) with the full transcript, the diff that finally fixed it, and the instruction: "Propose 3 short general rules that would have made the agent find this fix without the hint. No file names, function names, or line numbers."

Each candidate goes through:
1. **Generality check (deterministic).** Extract identifiers from the trap repo (file stems, function/class/variable names via `ast`, config keys from JSON). Reject any lesson that contains one, case-insensitively, as a whole word. Rejected lessons are stored with `status: "rejected", reason: "not_general"`.
2. **Vector dedupe (Atlas).** Embed with Voyage, `$vectorSearch` over `lessons`. If the top hit has cosine ≥ `0.90`, merge (append the source session id and bump `seen_count`) instead of inserting.

### 3.3 Bisect to the wrong turn
Definition: **the wrong turn is the first checkpoint from which the agent, with no lesson and no hint, can no longer recover** (baseline rescue ≤ 1/3).

- Checkpoints are `0..n-1`, where 0 is the opening message on clean code.
- `rescued(k)` = baseline replay from k succeeds in ≥ 2 of 3 seeds.
- Assume `rescued` is monotone: true early, false late. Binary search for the first k with `rescued(k) == false`. With 8 checkpoints that's about 3 probes × 3 seeds = 9 runs instead of 24.
- If `rescued(0)` is already false, wrong turn = 0 and the post-mortem says "the agent's first instinct was wrong." That's still a valid result, but a weaker demo, so trap tuning (§6) aims for the baseline to recover sometimes from k=0.
- Every probe is stored as a `runs` doc, so the report can show which checkpoints were tested.

### 3.4 Test lessons at the wrong turn
For each surviving lesson: 3 seeded replays from the wrong turn, all run in parallel alongside each other. Also run the best lesson at the **last** checkpoint (the most polluted context), which makes a strong demo line: "even after 20 turns of going in circles, one sentence gets it out." The best lesson has the highest rescue rate, with ties broken by fewer turns used.

### 3.5 Validate on held-out
Best lesson, fresh start (k=0, no history) on the held-out trap: 3 seeds with the lesson, 3 seeds without. That's 6 runs in parallel.

### 3.6 Adopt, reject, report
**Adopt** only if all three hold:
- rescue(lesson, wrong_turn) ≥ 2/3
- rescue(baseline, wrong_turn) ≤ 1/3
- held-out with ≥ held-out without

Otherwise **reject** and record which condition failed. On adopt, append the lesson to `out/AGENTS.md` under `## Proven lessons` with a one-line evidence note (`rescued 3/3 vs 0/3 at turn 4; held-out 2/3 vs 0/3`). Then generate `out/postmortem.md` and `out/report.html` from Atlas only.

**Run budget:** about 9 bisect runs + 9 lesson runs + 3 last-checkpoint runs + 6 held-out runs = **about 27 runs**. At about 3 minutes each with 8 in parallel, that's around 12 minutes. We precompute before recording the video.

---

## 4. Components and interfaces

Each module has one job, and the contracts below are fixed at the start so people can build in parallel against fakes. Package is renamed to `rekurse` (`src/rekurse/`). The existing `db.py` and `embeddings.py` move over unchanged.

```
src/rekurse/
  config.py       # env + constants (models, seeds, budgets, thresholds)
  pi_driver.py    # the only code that knows how to invoke Pi
  session.py      # parse Pi JSONL; find user-turn entries; truncate to fork
  workspace.py    # git init/commit/worktree; restore hidden tests; run tests
  trap.py         # load trap_repos/<name>/trap.yaml
  recorder.py     # record a painful session -> checkpoints
  reflector.py    # LLM -> candidate lessons; generality check; dedupe
  replay.py       # ONE replay run -> RunResult
  bisect.py       # find wrong turn; pure logic over a rescue() callback
  experiment.py   # schedule runs in parallel (asyncio + semaphore)
  decide.py       # adopt/reject; pure function
  store.py        # Store protocol + MongoStore + MemoryStore (tests)
  report.py       # postmortem.md + report.html from Store
  cli.py          # rekurse record|reflect|bisect|lessons|validate|report|demo|replay
  db.py, embeddings.py   # existing
trap_repos/
  primary/  heldout/
tests/
  fake_pi.py      # stand-in for the `pi` binary, scripted behaviour
  test_*.py
```

### 4.1 `pi_driver.py`
```python
@dataclass
class TurnResult:
    exit_code: int
    duration_s: float
    timed_out: bool
    tokens: int | None           # from --mode json output if available

def run_turn(workspace: Path, session_file: Path, message: str,
             model: str, timeout_s: int, seed: int) -> TurnResult
```
Runs `pi -p --mode json --session <session_file> --model <model> --approve --no-extensions --no-skills "<message>"` with `cwd=workspace` and an isolated `--session-dir`. The binary path comes from `REKURSE_PI_BIN` (default `pi`), which is how tests swap in `fake_pi.py`. Exact flags get confirmed in Phase 0 and written to `AGENTS.md`.

### 4.2 `session.py`
```python
def user_turn_entry_ids(session_file: Path) -> list[str]   # in order
def fork_before(session_file: Path, entry_id: str, dst: Path) -> Path
```
`fork_before` copies every entry up to, but not including, the user message at checkpoint k, and gives the new session a fresh session id. Pi then continues from that leaf when we send the replayed user message. Pure file manipulation, fully unit tested against a checked-in sample JSONL.

### 4.3 `workspace.py`
```python
def checkout(repo: Path, sha: str, dst: Path) -> Path        # git worktree add
def commit_all(workspace: Path, msg: str) -> str             # returns sha
def evaluate(workspace: Path, trap: Trap) -> TestResult      # passed, output
```
**Anti-cheat:** `evaluate` first restores the trap's `tests/` directory from the pristine trap source, then runs `trap.test_cmd`. An agent that edits the tests to make them pass gets no credit. This is covered by a test.

### 4.4 `replay.py`
```python
@dataclass
class ReplaySpec:
    trap: str; session_id: str | None; checkpoint_k: int     # k=0 + no session = fresh start
    lesson_id: str | None; seed: int; purpose: str           # "bisect"|"lesson"|"heldout"

@dataclass
class RunResult:
    success: bool; turns_used: int; duration_s: float
    tokens: int | None; final_test_output: str

def run(spec: ReplaySpec, store: Store) -> RunResult
```
Steps: temp dir, `checkout` at the checkpoint's sha, `fork_before` the recorded session, write the lesson into the workspace `AGENTS.md` (injection method A), then loop: send the checkpoint's user message (and afterwards the scripted follow-ups, **never the hint**), `evaluate` after every turn, stop on pass or after `REPLAY_MAX_TURNS` (default 4) user turns or `REPLAY_TIMEOUT_S` (default 300). Writes the `runs` doc. The original recording is never touched.

If Phase 0 shows Pi doesn't rebuild its system prompt from `AGENTS.md` for a continued session, switch to method B: prepend `"Note from past experience: <lesson>"` to the first replayed user message. It's a one-line change inside `replay.py`.

### 4.5 `bisect.py`
```python
def find_wrong_turn(n: int, rescued: Callable[[int], bool]) -> int
```
Pure function. Tests cover: always rescued (returns `n`, meaning "no wrong turn"), never rescued (0), a boundary at every position, and a non-monotone input (returns a valid boundary, documented).

### 4.6 `experiment.py`
```python
async def run_many(specs: list[ReplaySpec], store: Store, concurrency: int = 8) -> list[RunResult]
def rescue_rate(results: list[RunResult]) -> tuple[int, int]      # (successes, total)
```
`asyncio` plus a semaphore; each replay runs via `asyncio.to_thread` since the work is subprocesses. Each run is fully isolated (own worktree and session file), so there's no shared state.

### 4.7 `decide.py`
```python
def decide(lesson_at_wt: tuple[int,int], baseline_at_wt: tuple[int,int],
           heldout_with: tuple[int,int], heldout_without: tuple[int,int]) -> Decision
```
Pure; returns `adopted | rejected` plus the list of failed conditions. Table-driven tests.

### 4.8 `store.py`
A `Store` protocol with `MongoStore` (Atlas) and `MemoryStore` (dicts, with brute-force cosine for `similar_lessons`). Every other module talks to `Store`, never to pymongo directly. That's what lets the whole pipeline run in tests without a network.

---

## 5. Data model (Atlas, database `rekurse`)

| Collection | Shape |
|---|---|
| `sessions` | `{_id, trap, pi_session_path, agent_model, started_at, hint_turn, solved_turn, total_turns, solved_minutes}` |
| `checkpoints` | `{_id, session_id, k, git_sha, pi_entry_id, user_msg, is_hint}` |
| `lessons` | `{_id, text, status: candidate\|adopted\|rejected, reason, source_session_ids[], seen_count, embedding, scores{wrong_turn, last_turn, heldout_with, heldout_without}}` |
| `runs` | `{_id, session_id, trap, purpose, checkpoint_k, lesson_id\|null, seed, success, turns_used, tokens, duration_s, final_test_output, created_at}` |
| `reports` | `{_id, session_id, wrong_turn_k, bisect_probes[], best_lesson_id, decision, failed_conditions[], postmortem_md, created_at}` |

Vector index `lessons.embedding` (Voyage `voyage-3.5`, 1024 dims, cosine) via the existing `ensure_vector_index`. Nothing else needs an index at this scale.

---

## 6. Trap repos

Each trap is a tiny Python project with a `trap.yaml`:

```yaml
name: primary
test_cmd: "python -m pytest -q tests"
opening: "The test test_format_date is failing, please fix it."
followups: ["Still failing.", "That didn't fix it, try again.", "Tests still red."]
hint: "I think the value is coming from somewhere else, check how settings are loaded."
hint_after: 4          # user turns before the hint (recording only)
max_turns: 10
```

- **primary:** a date is formatted a day off. The failing assertion points at `format_date()`. The real cause is that `settings.py` loads the timezone from `config/defaults.json`, which silently overrides the env var. A second test pins `format_date()`'s behavior for explicit timezones, so "fixing" it at the symptom breaks that test.
- **heldout:** an invoice total is wrong. The assertion points at the rounding helper. The real cause is a stale `cache/rates.json` loaded before the live rate. The same second-test guard applies.

Shared mistake class: **patching the symptom instead of tracing where the input came from.**

Every trap ships with **self-tests** in our repo (`tests/test_traps.py`): (1) the pristine trap fails, (2) applying the known real fix (a stored `solution.patch`) passes, (3) applying the obvious symptom patch (a stored `symptom.patch`) still fails. This proves the trap is fair and the metric is real, without any LLM.

**Tuning target** (Phase 2, with the real agent model): baseline from k=0 succeeds sometimes, and baseline from late checkpoints almost never does. Knobs: more or fewer misleading comments near the symptom, how buried the config load is, and a weaker or stronger agent model (`REKURSE_AGENT_MODEL`).

---

## 7. Testing (the proof judges will read)

`uv run pytest` must pass offline in under 30 seconds. Layers:

1. **Pure logic:** `bisect`, `decide`, the generality check, `rescue_rate`, `session.fork_before` against a checked-in real Pi JSONL sample.
2. **Trap self-tests:** described in §6.
3. **Anti-cheat:** a fake agent that edits the tests to pass gets `success=False`.
4. **End-to-end with fake Pi:** `tests/fake_pi.py` accepts the same flags as `pi`, appends well-formed entries to the session file, and edits the workspace according to a rule:
   - it applies `symptom.patch` by default,
   - it applies `solution.patch` if the workspace `AGENTS.md` contains a trigger phrase, or if the message contains the hint.

   With `REKURSE_PI_BIN=tests/fake_pi.py` and `MemoryStore`, the full `record → reflect (stubbed LLM) → bisect → lessons → validate → decide → report` runs and asserts: wrong turn found, lesson adopted, the `AGENTS.md` block written, the report HTML contains the heatmap rows. This is the "does the harness do what it claims" test.
5. **Live smoke (not in CI):** `rekurse replay --trap primary --k 0 --lesson none --seed 1` against real Pi, and the existing `uv run smoke-test` for Atlas.

The README gets a short "How we know it works" section that points at these tests and at one real run's numbers in Atlas.

---

## 8. Outputs

- **`out/report.html`** (single file, inline CSS, no JS framework). Top to bottom:
  1. Headline: "Wrong turn: checkpoint 4 of 11. Lesson rescues 3/3 vs 0/3. Held-out: 2/3 vs 0/3. **Adopted.**"
  2. Timeline strip of the original session: one cell per user turn, the hint marked, the solve marked, minutes elapsed.
  3. Rescue grid: rows = baseline, each lesson; columns = checkpoints; cells show `n/3`, colored red to green; untested cells gray. Wrong turn column outlined.
  4. Held-out bars: with vs without.
  5. Lesson cards: text, status, reason, similarity merge info.
- **`out/postmortem.md`**: what happened, where it went wrong (with the agent's own message at the wrong turn quoted), the proven lesson, and the evidence table.
- **`out/AGENTS.md`**: the proven lessons block.

---

## 9. The 60 second video

| Time | Screen | Voiceover (roughly) |
|---|---|---|
| 0–8s | Recorded Pi session scrolling, "Still failing." ×6 | "Every engineer has lost an afternoon to an agent going in circles. And next week it happens again." |
| 8–20s | Terminal: `rekurse demo`, runs streaming, bisect probes | "Rekurse rewinds the session to every turn, forks the agent there, and replays it with and without a candidate lesson." |
| 20–38s | report.html: timeline + rescue grid, wrong turn outlined | "Here's the wrong turn. Without help, the agent never recovers: 0 out of 3. With this one sentence, 3 out of 3." |
| 38–48s | Held-out bars + `out/AGENTS.md` diff | "It also works on a bug it's never seen. Only then does it earn a place in AGENTS.md." |
| 48–60s | Atlas collections + `pytest` green | "Every session, run, and lesson lives in MongoDB, and Vector Search keeps memory from rotting. Other tools write lessons. We prove them." |

---

## 10. Team split and schedule

Interfaces in §4 are the contract. Everyone codes against `MemoryStore` and `fake_pi.py` until the real pieces land.

| Person | Owns | Critical? |
|---|---|---|
| **A: Harness** | Phase 0 Pi spike, `pi_driver`, `session`, `workspace`, `replay`, `experiment` | Yes, critical path |
| **B: Traps** | `trap_repos/primary`, `heldout`, patches, trap self-tests, `recorder`, trap tuning with the real model | Yes |
| **C: Brain + data** | `store` (Mongo + memory), vector index, `reflector` + generality check + dedupe, `bisect`, `decide`, `fake_pi.py`, e2e test | |
| **D: Story** | `report.py` HTML + post-mortem, README "How we know it works", video script, recording the video | |

With 3 people, C also takes D's `report.py` and the video becomes a shared last step. With 2 people: person 1 is A + C (harness + brain), person 2 is B + D (traps + story).

| Time | Milestone (done means) |
|---|---|
| 0:00–0:30 | **Phase 0.** Package rename; `uv run smoke-test` green. A: exact Pi commands for send / continue / fork-by-truncation verified from Python, and whether `AGENTS.md` is re-read on continue; written into `AGENTS.md`. B: primary trap + self-tests green. C: `Store` protocol + `MemoryStore`, `fake_pi.py` skeleton. |
| 0:30–1:30 | **Record + replay.** `rekurse record primary` stores a session and checkpoints. `rekurse replay --k 0 --lesson none --seed 1` runs and writes a `runs` doc. C: `bisect`, `decide`, generality check with tests. D: report from fixture data. |
| 1:30–2:15 | **Tune + reflect.** Baseline behaves as §6 targets (B + A). Reflector produces 3 lessons, deduped in Atlas (C). Held-out trap done (B). |
| 2:15–3:00 | **Full pipeline.** `rekurse demo --live` runs bisect, lessons, held-out, decide on real Pi. At least one lesson clears the adopt bar. The fake-Pi e2e test is green. |
| 3:00–3:30 | **Precompute + report.** Final live run stored in Atlas. `rekurse demo` (no `--live`) rebuilds the report from Atlas in seconds. README proof section. |
| 3:30–4:00 | **Video.** Record, re-record once, submit. Code freeze except fixes. |

**If we're behind, cut in this order:** report polish → last-checkpoint runs → vector dedupe (fall back to exact text match) → held-out validation (keep in pitch). **Never cut:** record, replay, bisect, tests.

---

## 11. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Pi can't continue a truncated session non-interactively | Use `--fork <file>` on the truncated copy. If that fails too, replay by sending a summarized transcript prefix as the first message (weaker, but still a fair comparison since baseline and lesson get the same prefix). Patching Pi source is the last resort. |
| `AGENTS.md` not re-read on continue | Injection method B (§4.4). |
| Trap too easy or too hard | Tuning knobs in §6. Decide by 2:15 at the latest; don't keep tuning after that. |
| Agent edits tests | Hidden-test restore in `evaluate` (§4.3). |
| Non-monotone baseline breaks bisect | Report shows every probed checkpoint with its n/3, so the claim stays honest. If time allows, probe one checkpoint on each side of the boundary. |
| Noise | Always show n/3, never a single run. Say "rescue rate", not "it works". |
| Pi project trust prompt blocks `-p` | `--approve` flag; confirm in Phase 0. |
| User-global Pi config (`~/.pi`) leaks into runs | Isolated `--session-dir`, `--no-extensions`, `--no-skills`; check whether a global `AGENTS.md` is loaded and disable it if so. |

---

## 12. Config

| Env var | Default | Purpose |
|---|---|---|
| `REKURSE_PI_BIN` | `pi` | tests set this to `tests/fake_pi.py` |
| `REKURSE_AGENT_MODEL` | picked in Phase 0 (cheap, trap-prone) | agent under test |
| `REKURSE_REFLECTOR_MODEL` | `claude-sonnet-5` | lesson proposals |
| `REKURSE_SEEDS` | `3` | runs per cell |
| `REKURSE_CONCURRENCY` | `8` | parallel replays |
| `REPLAY_MAX_TURNS` | `4` | user turns per replay |
| `REPLAY_TIMEOUT_S` | `300` | wall clock per replay |
| `DEDUPE_THRESHOLD` | `0.90` | cosine for merging lessons |
| `MONGODB_DB` | `rekurse` | database |

Note on seeds: most hosted models don't honor a seed, so "seed" is just the run index, used to keep run ids stable. The variation comes from sampling temperature, which is what we want.
