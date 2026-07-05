"""Layer 3 — the event controller (Humble Object).

Translates Claude Code's raw hook JSON into a domain `AgentEvent`, calls the use
case, and formats a small status dict back. It contains *no* business logic: the
decision of what mood to play lives in the domain, not here.

Claude Code delivers hook payloads shaped roughly like::

    {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {...}}
    {"hook_event_name": "PostToolUse", "tool_name": "Bash",
     "tool_response": {"stderr": "...", "is_error": true}}
    {"hook_event_name": "Stop", ...}
"""

from __future__ import annotations

from typing import Any

from ...domain.entities.events import AgentEvent
from ...domain.ports.clock import IClock
from ...domain.use_cases.handle_event import HandleAgentEventUseCase

# Claude Code hook_event_name -> our domain kind. Anything not listed maps to
# "ignore" (a no-op) so the ~20 lifecycle events we don't model never get
# misread as active work.
_KIND_BY_HOOK = {
    "PreToolUse": "tool_pre",
    "PostToolUse": "tool_post",
    "PostToolUseFailure": "tool_post",   # a failed tool -> classified as error below
    "Stop": "stop",
    "SubagentStop": "stop",
    "Notification": "notification",
    "PermissionRequest": "notification",  # agent is asking to use a tool -> alert
    "PermissionDenied": "notification",   # agent is blocked/waiting -> alert
    "Elicitation": "notification",        # agent is asking the human a question
    "SessionStart": "session_start",
    "UserPromptSubmit": "session_start",
}

# Hook events that always signal a tool failure regardless of payload shape.
_FAILURE_HOOKS = frozenset({"PostToolUseFailure"})


class EventController:
    def __init__(
        self, handle_event: HandleAgentEventUseCase, clock: IClock
    ) -> None:
        self._handle_event = handle_event
        self._clock = clock

    def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = self._to_event(payload)
        state = self._handle_event.execute(event)
        return {
            "intent": state.intent.value,
            "intensity": round(state.intensity, 3),
            "anxiety": round(state.anxiety, 3),
            "health": round(state.health, 3),
        }

    def _to_event(self, payload: dict[str, Any]) -> AgentEvent:
        hook_name = str(payload.get("hook_event_name", ""))
        kind = _KIND_BY_HOOK.get(hook_name, "ignore")
        tool = payload.get("tool_name")
        is_error = hook_name in _FAILURE_HOOKS or self._detect_error(payload)
        return AgentEvent(
            kind=kind,
            tool=str(tool) if tool else None,
            is_error=is_error,
            at=self._clock.now(),
            target=self._extract_target(payload),
            message=self._extract_message(payload, hook_name, tool),
        )

    @staticmethod
    def _extract_message(payload, hook_name: str, tool) -> str | None:
        """Human-readable note for 'needs you' announcements."""
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        if hook_name in ("PermissionRequest", "PermissionDenied"):
            return f"Claude needs permission to use {tool}" if tool else (
                "Claude needs your permission"
            )
        if hook_name == "Elicitation":
            return "Claude has a question for you"
        if hook_name == "Notification":
            return "Claude needs your attention"
        return None

    # Keys in tool_input that identify *what* a tool acted on, so we can spot the
    # agent hammering the same file/command (a stuck loop).
    _TARGET_KEYS = ("file_path", "path", "notebook_path", "command", "pattern", "url", "query")

    @classmethod
    def _extract_target(cls, payload: dict[str, Any]) -> str | None:
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return None
        for key in cls._TARGET_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]  # normalise/truncate long commands
        return None

    @staticmethod
    def _detect_error(payload: dict[str, Any]) -> bool:
        # PostToolUseFailure carries a top-level tool_error.
        if payload.get("tool_error"):
            return True
        response = payload.get("tool_response")
        if isinstance(response, dict):
            if response.get("is_error") or response.get("error") or response.get("tool_error"):
                return True
            stderr = response.get("stderr")
            if isinstance(stderr, str) and stderr.strip():
                return True
        return False
