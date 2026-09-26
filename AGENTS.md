# AGENTS.md

Instructions for coding agents (Pi, Claude Code, Codex, Cursor). `CLAUDE.md` is a symlink to this file.

## Project
MongoDB Agentic Memory Hackathon (NYC, Sep 26 2026). Theme: memory, persistence and self-evolving agent **harnesses**.
- **Rekurse**: finds the turn where a coding agent (Pi) went wrong, and proves which one-sentence AGENTS.md rule would have saved it.
- Problem statement: #1 Recursive Harnessing.
- **Design spec (source of truth):** `docs/superpowers/specs/2026-09-26-rekurse-design.md`. Original brief: `docs/brief.md`.

## Stack
- Python 3.13, managed with **uv** (`uv add <pkg>`, `uv run <cmd>`). Never use pip directly.
- MongoDB Atlas via `pymongo`: Vector Search, aggregation, Change Streams.
- Embeddings: Voyage AI (`voyage-3.5`, 1024 dims), OpenAI fallback. See `src/rekurse/embeddings.py`.
- LLMs: Anthropic / OpenAI SDKs. Keys come from `.env` (see `.env.example`).
- Shared helpers: `src/rekurse/db.py` (`get_db`, `ensure_vector_index`, `vector_search`). Package is `src/rekurse/`; see README Layout.
- Agent under test: Pi CLI, driven by `src/rekurse/harness.py`. Tests use `tests/fake_pi.py` (same flags, scripted).

## Rules
- Hackathon scope: one clear problem, done deep and stable. Don't add features that don't serve the one-liner.
- Never commit secrets or `.env`. Never hard-code connection strings or API keys.
- Small, focused commits; pull before pushing (`git pull --rebase`). Work on short-lived branches or coordinate on `main`.
- Every new collection that needs similarity search gets its index via `ensure_vector_index`.
- Keep the demo runnable at all times: `uv run smoke-test` must pass.

## Team
Yvonne (full-stack, demo UI) · Harry (agents, LLM, memory tooling) · Sabrina (data, benchmark, metrics) · Lin (data layer, schema, indexes) · Guy (SDE)

## Pi invocation (verified 0.87.1)
```
pi -p --mode json --session <file.jsonl> --session-dir <dir> --model anthropic/<id> \
   --approve --no-extensions --no-skills --no-context-files \
   --append-system-prompt "<lesson or placebo>" -- "<user message>"
```
- `--mode json` exits 0 even on API errors. Success = last assistant `message_end.stopReason` in {stop, toolUse}; `stopReason: error` carries `errorMessage`.
- Session file v3: header `{type: session, version: 3, id, cwd}` then entries `{type, id, parentId, ...}`; user turns are `type: message` with `message.role: user`. Fork = truncate copy before user entry k, new header id, rewrite `cwd` and all workspace paths.
- Always pass `--model`; global default is Opus. `--no-context-files` stops our own AGENTS.md leaking into the agent under test.
- Auth: default agent model is `openai/gpt-4.1-mini`, so `OPENAI_API_KEY` must be in `.env`. Override with `REKURSE_AGENT_MODEL=anthropic/claude-haiku-4-5-20251001` (needs `ANTHROPIC_API_KEY`; the Pi OAuth login has no extra usage).
- Reflector and embeddings follow the keys present: Anthropic + Voyage if set, otherwise OpenAI for both (`text-embedding-3-small`, 1536 dims).
