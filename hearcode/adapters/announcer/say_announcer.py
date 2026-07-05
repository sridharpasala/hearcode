"""Layer 3 — speak to the human via the macOS `say` command.

Fire-and-forget subprocess so the HTTP handler never blocks, with a short
debounce so a burst of notifications doesn't talk over itself.
"""

from __future__ import annotations

import subprocess
import time

from ...domain.ports.announcer import IAnnouncer


class SayAnnouncer(IAnnouncer):
    def __init__(self, voice: str | None = None, debounce_seconds: float = 4.0) -> None:
        self._voice = voice
        self._debounce = debounce_seconds
        self._last = 0.0

    def set_voice(self, voice: str | None) -> None:
        """Switch the `say` voice for subsequent announcements (live)."""
        self._voice = voice or None

    def announce(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last < self._debounce:
            return
        self._last = now
        cmd = ["say"]
        if self._voice:
            cmd += ["-v", self._voice]
        cmd.append(message.strip()[:140])
        try:
            subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
