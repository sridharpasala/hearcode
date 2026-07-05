"""Layer 3 — the Null Object audio adapter.

Used when no audio device is available (CI, headless, --silent) or when
sounddevice/numpy fail to import. It satisfies IAudioMixer and does nothing
harmful, so the rest of the system never needs `if audio_available:` checks.
Optionally logs transitions so you can still *see* the soundtrack decisions.
"""

from __future__ import annotations

from ...domain.entities.intent import Intent
from ...domain.entities.musical_state import MusicalState
from ...domain.ports.audio import IAudioMixer


class NullMixer(IAudioMixer):
    def __init__(self, on_change=None) -> None:
        # on_change: optional callback(str) for surfacing transitions in logs.
        self._on_change = on_change
        self._last: MusicalState | None = None

    def render(self, state: MusicalState) -> None:
        if self._on_change and (
            self._last is None
            or state.intent != self._last.intent
            or abs(state.intensity - self._last.intensity) >= 0.25
            or abs(state.anxiety - self._last.anxiety) >= 0.25
            or abs(state.health - self._last.health) >= 0.15
        ):
            anx = f"  anxiety={state.anxiety:.2f}" if state.anxiety > 0 else ""
            health = "" if abs(state.health - 0.5) < 0.01 else f"  health={state.health:.2f}"
            self._on_change(
                f"♪ {state.intent.value:<8} intensity={state.intensity:.2f}{anx}{health}"
            )
        self._last = state

    def accent(self, intent: Intent) -> None:
        if self._on_change:
            self._on_change(f"  · accent: {intent.value}")

    def motif(self, tool: str | None) -> None:
        if self._on_change and tool:
            self._on_change(f"  ♪ motif: {tool}")

    def set_stems(self, stems_dir) -> None:  # noqa: ANN001
        # No audio to reload — the theme is purely cosmetic here.
        if self._on_change:
            self._on_change(f"  ♪ theme stems -> {stems_dir}")

    def set_loop(self, name, buffer) -> None:  # noqa: ANN001
        # No audio to swap — the pad ambience is a no-op without a device.
        if self._on_change:
            self._on_change(f"  ♪ loop swap -> {name}")

    def shutdown(self) -> None:
        pass
