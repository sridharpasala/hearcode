"""Layer 1 — the agent activity that flows through the system.

`AgentEvent` is the domain's normalised view of "something happened in the
agent." It is deliberately ignorant of HTTP, of Claude Code's hook JSON shape,
and of how it was transported here. Adapters translate the outside world into
this value object at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

# The transport-neutral families of agent activity we recognise.
# "ignore" is a no-op family for lifecycle events that should not move the music.
KINDS = (
    "tool_pre",
    "tool_post",
    "stop",
    "notification",
    "session_start",
    "idle",
    "ignore",
)


@dataclass(frozen=True)
class AgentEvent:
    """One thing the agent did, in domain terms.

    kind:     one of KINDS — the lifecycle family of the event.
    tool:     the tool name when kind is tool_pre/tool_post, else None.
    is_error: True when a tool reported a failure.
    at:       monotonic timestamp (seconds) when the event was observed.
    """

    kind: str
    tool: str | None
    is_error: bool
    at: float
    target: str | None = None   # fingerprint of what was acted on (path/command/…)
    message: str | None = None  # human-readable note (e.g. why the agent needs you)

    @property
    def is_work(self) -> bool:
        """A unit of active work that should count toward intensity."""
        return self.kind == "tool_pre"

    @property
    def signature(self) -> str | None:
        """Stable id of this action, for spotting repetition (stuck loops)."""
        if self.tool is None:
            return None
        return f"{self.tool}:{self.target}" if self.target else self.tool
