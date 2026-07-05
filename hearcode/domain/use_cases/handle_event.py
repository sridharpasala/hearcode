"""Layer 2 — the central use case: react to one agent event.

One user intention: *"When the agent does something, the soundtrack should
reflect it."* Orchestrates the session entity and the output ports. Returns the
resulting MusicalState (a domain value) — never a dict, string, or HTTP shape.
"""

from __future__ import annotations

from ..entities.events import AgentEvent
from ..entities.intent import Intent
from ..entities.musical_state import MusicalState
from ..entities.session import SessionState
from ..entities.session_entry import SessionEntry
from ..ports.announcer import IAnnouncer
from ..ports.audio import IAudioMixer
from ..ports.session_log import ISessionLog

# Spoken when the agent is blocked but gave no specific message.
DEFAULT_NEEDS_YOU = "Claude needs your attention"

# Anxiety at/above this fires the one-shot "you're stuck" alert (edge-triggered).
STUCK_ALERT = 0.6


class HandleAgentEventUseCase:
    def __init__(
        self,
        session: SessionState,
        mixer: IAudioMixer,
        announcer: IAnnouncer,
        session_log: ISessionLog,
    ) -> None:
        self._session = session
        self._mixer = mixer
        self._announcer = announcer
        self._log = session_log
        self._was_stuck = False

    def execute(self, event: AgentEvent) -> MusicalState:
        state = self._session.observe(event)
        if event.kind == "ignore":
            return state  # nothing changed; don't render or record

        cues: list[str] = []
        # Transient one-shots layered over the continuous mood.
        if event.is_error:
            self._mixer.accent(Intent.ERROR)
            cues.append("error")
        elif event.kind == "stop":
            self._mixer.accent(Intent.DONE)
            cues.append("done")
        elif event.kind == "notification":
            # The agent is blocked, waiting on the human: alert + speak.
            self._mixer.accent(Intent.NEEDS_INPUT)
            self._announcer.announce(event.message or DEFAULT_NEEDS_YOU)
            cues.append("needs_input")
        elif event.kind == "tool_pre":
            # Per-tool leitmotif: you can hear *which* tool the agent reached for.
            self._mixer.motif(event.tool)
            if event.tool:
                cues.append(f"motif:{event.tool}")

        # Alert once when the agent first looks stuck (not on every event while
        # it stays stuck), and re-arm only after anxiety subsides.
        stuck_now = state.anxiety >= STUCK_ALERT
        if stuck_now and not self._was_stuck:
            self._mixer.accent(Intent.STUCK)
            cues.append("stuck")
        self._was_stuck = stuck_now

        self._mixer.render(state)
        self._log.record(
            SessionEntry(
                at=event.at,
                kind=event.kind,
                intent=state.intent.value,
                intensity=state.intensity,
                anxiety=state.anxiety,
                health=state.health,
                tool=event.tool,
                cues=tuple(cues),
            )
        )
        return state
