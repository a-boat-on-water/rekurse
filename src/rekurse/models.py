"""Dataclasses, config constants and trap loading. Single source of truth for shapes."""
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
TRAP_ROOT = ROOT / "trap_repos"
OUT_DIR = Path(os.environ.get("REKURSE_OUT", ROOT / "out"))

PI_BIN: list[str] = shlex.split(os.environ.get("REKURSE_PI_BIN", "pi"))
# Agent under test: cheap and trap-prone. Pi model ids are "provider/id"; it needs the matching API key in the env.
AGENT_MODEL = os.environ.get("REKURSE_AGENT_MODEL", "openai/gpt-4.1-mini")
# Reflector: Anthropic if a key is present, else OpenAI. Plain model id, used via the provider SDK directly.
_HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY"))
REFLECTOR_MODEL = os.environ.get("REKURSE_REFLECTOR_MODEL", "claude-sonnet-5" if _HAS_ANTHROPIC else "gpt-4.1")
SEEDS = int(os.environ.get("REKURSE_SEEDS", "3"))
DECISION_SEEDS = int(os.environ.get("REKURSE_DECISION_SEEDS", "5"))
CONCURRENCY = int(os.environ.get("REKURSE_CONCURRENCY", "4"))
REPLAY_MAX_TURNS = int(os.environ.get("REPLAY_MAX_TURNS", "2"))
TURN_TIMEOUT_S = int(os.environ.get("TURN_TIMEOUT_S", "240"))
# Tools the agent under test may use. No bash: the agent cannot run the tests or grep, so it must reason from
# what it reads and only learns whether it worked from the user's next message. Same for baseline and lesson arms.
PI_TOOLS = os.environ.get("REKURSE_PI_TOOLS", "read,edit,write")
# voyage-3.5 puts distinct one-sentence rules at cos 0.90-0.93; only near-paraphrases score above 0.96.
DEDUPE_THRESHOLD = float(os.environ.get("DEDUPE_THRESHOLD", "0.96"))
MONGODB_DB = os.environ.get("MONGODB_DB", "rekurse")

PLACEBO = "Follow the project's existing conventions and keep changes minimal."


@dataclass
class Trap:
    name: str
    test_cmd: str
    opening: str
    followups: list[str]
    hint: str
    hint_after: int
    max_turns: int
    trigger_phrase: str
    path: Path

    @property
    def pristine(self) -> Path:
        return self.path / "pristine"

    def overlay(self, kind: str) -> Path:
        return self.path / kind


def load_trap(name: str) -> Trap:
    path = TRAP_ROOT / name
    data = json.loads((path / "trap.json").read_text())
    return Trap(path=path, **data)


@dataclass
class TurnResult:
    ok: bool
    stop_reason: str | None
    tokens: int | None
    duration_s: float
    timed_out: bool
    error: str | None = None
    assistant_text: str = ""


@dataclass
class TestResult:
    passed: bool
    output: str


@dataclass
class Checkpoint:
    session_id: str
    k: int
    git_sha: str
    user_msg: str
    is_hint: bool
    agent_msg_excerpt: str = ""

    @property
    def _id(self) -> str:
        return f"{self.session_id}:{self.k}"


@dataclass
class ReplaySpec:
    run_group: str
    trap: str
    session_id: str | None      # None => fresh start on pristine trap
    checkpoint_k: int
    lesson_id: str | None
    lesson_text: str | None
    seed: int
    purpose: str                # sweep | decision | lesson | heldout | spike
    attempt: int = 1

    @property
    def run_id(self) -> str:
        return f"{self.run_group}:{self.trap}:{self.checkpoint_k}:{self.lesson_id or 'base'}:{self.seed}:{self.attempt}"


@dataclass
class RunResult:
    spec: ReplaySpec
    success: bool
    turns_used: int
    duration_s: float
    tokens: int | None
    stop_reason: str | None
    timed_out: bool
    final_test_output: str
    agent_model: str = AGENT_MODEL

    @property
    def counted(self) -> bool:
        """Timed-out or errored runs are excluded from rescue rates."""
        return not self.timed_out and self.stop_reason not in ("error", "aborted")

    def to_doc(self) -> dict:
        s = self.spec
        return {
            "_id": s.run_id, "run_group": s.run_group, "session_id": s.session_id, "trap": s.trap,
            "purpose": s.purpose, "checkpoint_k": s.checkpoint_k, "lesson_id": s.lesson_id,
            "lesson_text": s.lesson_text, "seed": s.seed, "attempt": s.attempt,
            "agent_model": self.agent_model, "success": self.success, "stop_reason": self.stop_reason,
            "timed_out": self.timed_out, "turns_used": self.turns_used, "tokens": self.tokens,
            "duration_s": self.duration_s, "final_test_output": self.final_test_output[-4000:],
        }


@dataclass
class Decision:
    adopted: bool
    failed_conditions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
