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
- Embeddings: Voyage AI (`voyage-3.5`, 1024 dims), OpenAI fallback. See `src/agent_memory_hackathon/embeddings.py`.
- LLMs: Anthropic / OpenAI SDKs. Keys come from `.env` (see `.env.example`).
- Shared helpers: `src/agent_memory_hackathon/db.py` (`get_db`, `ensure_vector_index`, `vector_search`).

## Rules
- Hackathon scope: one clear problem, done deep and stable. Don't add features that don't serve the one-liner.
- Never commit secrets or `.env`. Never hard-code connection strings or API keys.
- Small, focused commits; pull before pushing (`git pull --rebase`). Work on short-lived branches or coordinate on `main`.
- Every new collection that needs similarity search gets its index via `ensure_vector_index`.
- Keep the demo runnable at all times: `uv run smoke-test` must pass.

## Team
Yvonne (full-stack, demo UI) · Harry (agents, LLM, memory tooling) · Sabrina (data, benchmark, metrics) · Lin (data layer, schema, indexes) · Guy (SDE)
