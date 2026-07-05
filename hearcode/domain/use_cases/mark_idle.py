"""Layer 2 — decay to silence when the agent goes quiet.

One user intention: *"If nothing has happened for a while, fade the music down."*
Driven by a timer in the outer layer, but the *rule* (how long is "a while", what
idle means musically) lives here in the application layer.
"""

from __future__ import annotations

from ..entities.events import AgentEvent
from ..entities.musical_state import MusicalState
from ..entities.session import SessionState
from ..ports.audio import IAudioMixer
from ..ports.clock import IClock


class MarkIdleUseCase:
    def __init__(
        self,
        session: SessionState,
        mixer: IAudioMixer,
        clock: IClock,
        idle_after_seconds: float = 20.0,
    ) -> None:
        self._session = session
        self._mixer = mixer
        self._clock = clock
        self._idle_after = idle_after_seconds

    def execute(self) -> MusicalState:
        now = self._clock.now()
        if self._session.seconds_since_last_event(now) < self._idle_after:
            return self._session.current()  # still active — leave the mood alone

        idle_event = AgentEvent(kind="idle", tool=None, is_error=False, at=now)
        state = self._session.observe(idle_event)
        self._mixer.render(state)
        return state
