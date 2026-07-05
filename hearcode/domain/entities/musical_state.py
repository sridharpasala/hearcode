"""Layer 1 — the soundtrack target the domain emits.

`MusicalState` is what the domain *decides*; how it is rendered into actual
stems and volumes is an adapter concern (a different stem pack would arrange the
same MusicalState differently). The domain speaks only of intent + intensity.
"""

from __future__ import annotations

from dataclasses import dataclass

from .intent import Intent


@dataclass(frozen=True)
class MusicalState:
    """The mood the soundtrack should currently express.

    intent:    the qualitative mood.
    intensity: 0.0 .. 1.0 — how energetic/busy the work is right now.
    anxiety:   0.0 .. 1.0 — how "stuck" the agent seems (errors + repetition).
               Layered as unease *over* whatever the intent is.
    health:    0.0 .. 1.0 — build health from the last test/build outcome.
               1 = green (bright/major), 0 = red (dark/minor), 0.5 = unknown.
    """

    intent: Intent
    intensity: float
    anxiety: float = 0.0
    health: float = 0.5

    def __post_init__(self) -> None:
        object.__setattr__(self, "intensity", _clamp(self.intensity))
        object.__setattr__(self, "anxiety", _clamp(self.anxiety))
        object.__setattr__(self, "health", _clamp(self.health))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
