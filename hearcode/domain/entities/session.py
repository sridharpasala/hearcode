"""Layer 1 — the live state of one agent session.

`SessionState` owns the only mutable domain state: rolling windows of recent
activity used to derive intensity and "anxiety" (stuck-loop pressure), plus the
most recent musical decision. It is pure (stdlib only) and fully unit-testable
without any audio or network.
"""

from __future__ import annotations

from collections import Counter, deque

from .events import AgentEvent
from .intent import Intent, classify, is_build_check
from .musical_state import MusicalState

# Stuck-loop tuning: how much repetition / error pressure means "fully stuck".
STUCK_WINDOW = 30.0   # seconds — doom loops play out slower than intensity
STUCK_ERRORS = 3      # this many recent failures == full error pressure
STUCK_REPEATS = 4     # same action target this many times == full repetition

# Build-health tuning: how far each test/build outcome moves the harmony.
HEALTH_NEUTRAL = 0.5  # unknown until the first test/build runs
HEALTH_UP = 0.6       # a pass brightens toward green
HEALTH_DOWN = 0.7     # a fail darkens toward red (a little faster)


class SessionState:
    """Folds a stream of AgentEvents into the current MusicalState."""

    def __init__(
        self,
        window_seconds: float = 10.0,
        saturation: int = 8,
        stuck_window_seconds: float = STUCK_WINDOW,
    ) -> None:
        # `saturation` work-events within `window_seconds` == full intensity.
        self._window = float(window_seconds)
        self._saturation = max(1, saturation)
        self._stuck_window = float(stuck_window_seconds)
        self._work_times: deque[float] = deque()
        # (at, signature) of recent *failures* — both the streak length and
        # whether the same thing keeps failing drive the stuck-loop signal.
        self._failures: deque[tuple[float, str | None]] = deque()
        self._health = HEALTH_NEUTRAL  # build health — persists across the session
        self._last_event_at: float = 0.0
        self._current = MusicalState(Intent.IDLE, 0.0)

    def observe(self, event: AgentEvent) -> MusicalState:
        """Record an event and return the new MusicalState."""
        # Unrecognised lifecycle events leave the soundtrack untouched and do not
        # reset the idle timer — they are not "activity."
        if event.kind == "ignore":
            return self._current
        self._last_event_at = event.at

        if event.is_work:
            self._work_times.append(event.at)
        if event.is_error:
            self._failures.append((event.at, event.signature))
        self._update_health(event)
        self._evict_old(event.at)

        intent = classify(event)
        intensity = self._intensity()
        anxiety = self._anxiety()

        if intent in (Intent.DONE, Intent.IDLE):
            # Finishing / going quiet resolves the tension entirely — but build
            # health persists (a green build stays green while the agent rests).
            intensity = 0.0
            anxiety = 0.0
            self._failures.clear()

        self._current = MusicalState(intent, intensity, anxiety, self._health)
        return self._current

    def _update_health(self, event: AgentEvent) -> None:
        # Health only moves on the *outcome* of a test/build/lint command.
        if event.kind != "tool_post" or not is_build_check(event.target):
            return
        target = 0.0 if event.is_error else 1.0
        rate = HEALTH_DOWN if event.is_error else HEALTH_UP
        self._health += rate * (target - self._health)

    def current(self) -> MusicalState:
        return self._current

    def seconds_since_last_event(self, now: float) -> float:
        if self._last_event_at == 0.0:
            return float("inf")
        return now - self._last_event_at

    def _intensity(self) -> float:
        return min(1.0, len(self._work_times) / self._saturation)

    def _anxiety(self) -> float:
        """Stuck-loop pressure, driven entirely by recent *failures*.

        Productive iteration (repeated edits with no failures) stays calm. A
        single error is mild. A streak builds pressure, and the *same thing
        failing over and over* — the classic doom loop — escalates fastest.
        """
        if not self._failures:
            return 0.0
        error_pressure = min(1.0, len(self._failures) / STUCK_ERRORS)
        top_repeat = self._top_failing_repeat()
        repetition = min(1.0, (top_repeat - 1) / (STUCK_REPEATS - 1))
        return min(1.0, error_pressure + 0.5 * repetition)

    def _top_failing_repeat(self) -> int:
        """How many times the most-repeated failing target has failed."""
        signatures = [sig for _, sig in self._failures if sig]
        if not signatures:
            return 0
        return Counter(signatures).most_common(1)[0][1]

    def _evict_old(self, now: float) -> None:
        cutoff = now - self._window
        while self._work_times and self._work_times[0] < cutoff:
            self._work_times.popleft()
        stuck_cutoff = now - self._stuck_window
        while self._failures and self._failures[0][0] < stuck_cutoff:
            self._failures.popleft()
