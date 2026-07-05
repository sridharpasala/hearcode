"""Layer 1 — one recorded moment of a session's soundtrack.

A flat, serialisable snapshot of the musical decision for a single event, plus
the cues that fired. A sequence of these *is* the session's soundtrack timeline —
enough to compute a recap (stats) and to re-render the audio offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SessionEntry:
    at: float                 # monotonic seconds (only differences matter)
    kind: str                 # the AgentEvent kind that produced this moment
    intent: str               # MusicalState.intent value
    intensity: float
    anxiety: float
    health: float
    tool: str | None = None
    cues: tuple[str, ...] = field(default_factory=tuple)  # e.g. ("motif:Edit",), ("stuck",)
