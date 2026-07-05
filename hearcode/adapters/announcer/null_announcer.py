"""Layer 3 — the Null Object announcer (no speech / headless / disabled).

Optionally logs what *would* have been spoken, which is handy in --silent demos.
"""

from __future__ import annotations

from ...domain.ports.announcer import IAnnouncer


class NullAnnouncer(IAnnouncer):
    def __init__(self, on_change=None) -> None:
        self._on_change = on_change

    def announce(self, message: str) -> None:
        if self._on_change:
            self._on_change(f"  🗣  says: \"{message}\"")

    def set_voice(self, voice) -> None:  # noqa: ANN001
        # No speech to reconfigure; accept the call so the control plane is uniform.
        if self._on_change:
            self._on_change(f"  🗣  voice -> {voice or 'system default'}")
