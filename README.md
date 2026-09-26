# agent-memory-hackathon

MongoDB Agentic Memory Hackathon — NYC, Sep 26 2026. Project idea TBD (picked 9:15am).

## Setup (5 min)

Needs Python via [uv](https://docs.astral.sh/uv/) (`brew install uv`) and Git.

```bash
git clone https://github.com/a-boat-on-water/agent-memory-hackathon.git
cd agent-memory-hackathon
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
src/agent_memory_hackathon/
  db.py          # Atlas connection, vector index + search helpers
  embeddings.py  # Voyage AI / OpenAI embeddings
  smoke_test.py  # end-to-end environment check
```
