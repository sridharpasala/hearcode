"""Layer 1 — the core domain concept: what *kind* of work the agent is doing.

`Intent` is the enterprise-wide vocabulary HearCode reasons in. It would remain
meaningful even if there were no audio, no HTTP, and no Claude Code hooks at all.
The `classify` function encodes the one piece of enterprise policy that never
changes: how a unit of agent activity maps to a musical intent.
"""

from __future__ import annotations

from enum import Enum

from .events import AgentEvent


class Intent(Enum):
    """A musical intent — the mood the soundtrack should express."""

    EXPLORE = "explore"   # reading / searching the codebase
    BUILD = "build"       # writing / editing code
    ACTION = "action"     # running commands, delegating to subagents
    TENSION = "tension"   # long-running / risky work
    ERROR = "error"       # a tool reported a failure
    STUCK = "stuck"       # spinning: repeated failures on the same target
    NEEDS_INPUT = "needs_input"  # blocked, waiting on the human (alert them!)
    IDLE = "idle"         # nothing happening / waiting on the human
    DONE = "done"         # the agent finished its turn


# Tool-name → intent policy. Names match Claude Code's tool vocabulary.
_EXPLORE_TOOLS = frozenset(
    {"Read", "Grep", "Glob", "LS", "NotebookRead", "WebFetch", "WebSearch", "ToolSearch"}
)
_BUILD_TOOLS = frozenset(
    {"Edit", "Write", "MultiEdit", "NotebookEdit", "Update", "ApplyPatch"}
)
_ACTION_TOOLS = frozenset({"Bash", "Task", "Agent", "Workflow", "Skill"})


# Command/target fragments that mean "the agent just checked the build/tests".
# Their pass/fail outcome drives the build-health harmony (major vs minor color).
_BUILD_CHECK_PATTERNS = (
    "pytest", "unittest", "nox", "tox", "npm test", "yarn test", "pnpm test",
    "jest", "vitest", "mocha", "go test", "cargo test", "cargo build", "rspec",
    "phpunit", "npm run build", "tsc", "mypy", "ruff", "eslint", "flake8",
    "gradle", "mvn ", "make ", "rake",
)


def is_build_check(target: str | None) -> bool:
    """True if this action is running tests / a build / a linter (pure policy)."""
    if not target:
        return False
    text = target.lower()
    return any(pattern in text for pattern in _BUILD_CHECK_PATTERNS)


def classify(event: AgentEvent) -> Intent:
    """Map a single agent event onto a musical intent (pure policy, no I/O)."""
    if event.kind == "stop":
        return Intent.DONE
    if event.kind == "idle":
        return Intent.IDLE
    if event.is_error:
        return Intent.ERROR
    if event.kind == "notification":
        # Agent is waiting on the human — duck to a quiet bed.
        return Intent.IDLE
    if event.kind == "session_start":
        return Intent.EXPLORE

    tool = event.tool or ""
    if tool in _BUILD_TOOLS:
        return Intent.BUILD
    if tool in _ACTION_TOOLS:
        return Intent.ACTION
    if tool in _EXPLORE_TOOLS:
        return Intent.EXPLORE
    return Intent.EXPLORE
