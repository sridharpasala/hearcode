"""Layer 3 — the real clock adapter."""

from __future__ import annotations

import time

from ...domain.ports.clock import IClock


class SystemClock(IClock):
    def now(self) -> float:
        return time.monotonic()
