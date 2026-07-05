"""Layer 1b — the clock port.

Time is an external dependency like any other. Use cases that need "now" depend
on this abstraction, never on `time.monotonic()` directly, so tests can supply a
deterministic fake clock.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IClock(ABC):
    @abstractmethod
    def now(self) -> float:
        """Monotonic seconds. Only differences are meaningful."""
