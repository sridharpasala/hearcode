"""Layer 4 — the composition root.

The one place that imports every concrete class and wires them together. Every
other module depends only on abstractions; here those abstractions become real
instances. If audio can't initialise, we degrade to the NullMixer so the rest of
the system runs unchanged (Null Object pattern).
"""

from __future__ import annotations

import platform

from ..adapters.announcer.null_announcer import NullAnnouncer
from ..adapters.clock.system_clock import SystemClock
from ..adapters.http.controller import EventController
from ..adapters.mixer.null_mixer import NullMixer
from ..domain.entities.session import SessionState
from ..domain.ports.announcer import IAnnouncer
from ..domain.ports.audio import IAudioMixer
from ..domain.ports.session_log import ISessionLog
from ..domain.use_cases.handle_event import HandleAgentEventUseCase
from ..domain.use_cases.mark_idle import MarkIdleUseCase
from .config import Config


class Container:
    def __init__(self, config: Config, log=print) -> None:
        self._config = config
        self._log = log

        self._theme = config.theme  # the live theme (mutable; set_theme swaps it)
        self._voice = config.voice  # the live TTS voice (mutable; set_voice swaps it)
        self._pad_style = config.pad_style  # live pad ambience (set_pad_style swaps it)
        self.clock = SystemClock()
        self.session = SessionState(
            window_seconds=config.window_seconds, saturation=config.saturation
        )
        self.mixer: IAudioMixer = self._build_mixer()
        # The live pad is synthesized from the selected ambience at startup, so it
        # is authoritative over whatever pad.wav happens to be cached on disk
        # (keeps upgrades correct). Skip in silent mode — no audio to shape.
        if not self._config.silent and getattr(self.mixer, "set_loop", None):
            self._apply_pad(self._pad_style)
        self.announcer: IAnnouncer = self._build_announcer()
        self.session_log: ISessionLog = self._build_session_log()

        self.handle_event = HandleAgentEventUseCase(
            self.session, self.mixer, self.announcer, self.session_log
        )
        self.mark_idle = MarkIdleUseCase(
            self.session, self.mixer, self.clock, config.idle_after_seconds
        )
        self.controller = EventController(self.handle_event, self.clock)

    def _build_mixer(self) -> IAudioMixer:
        if self._config.silent:
            self._log("audio: silent mode — using NullMixer (decisions logged)")
            return NullMixer(on_change=self._log)
        try:
            from ..adapters.mixer.sounddevice_mixer import SounddeviceMixer
            from ..adapters.mixer.stem_pack import ensure_assets

            self._log(f"audio: theme '{self._config.theme}'")
            stems_dir = ensure_assets(
                self._config.assets_dir, self._config.theme, self._log
            )
            return SounddeviceMixer(
                assets_dir=stems_dir,
                fade_seconds=self._config.fade_seconds,
                master=self._config.volume,
                leitmotifs=self._config.leitmotifs,
            )
        except Exception as exc:  # missing deps, no device, or no assets
            self._log(f"audio: falling back to NullMixer ({exc})")
            return NullMixer(on_change=self._log)

    def _build_announcer(self) -> IAnnouncer:
        if not self._config.announce:
            return NullAnnouncer()
        # In silent/headless mode, log what would be spoken instead of speaking.
        if not self._config.silent and platform.system() == "Darwin":
            from ..adapters.announcer.say_announcer import SayAnnouncer

            return SayAnnouncer(voice=self._config.voice)
        return NullAnnouncer(on_change=self._log)

    def _build_session_log(self) -> ISessionLog:
        if not self._config.record:
            from ..adapters.session_log.null_session_log import NullSessionLog

            return NullSessionLog()
        try:
            from ..adapters.session_log.jsonl_session_log import JsonlSessionLog

            log = JsonlSessionLog(self._config.sessions_dir)
            self._log(f"recording: session timeline -> {self._config.sessions_dir}")
            return log
        except Exception as exc:
            from ..adapters.session_log.null_session_log import NullSessionLog

            self._log(f"recording: disabled ({exc})")
            return NullSessionLog()

    def set_theme(self, theme: str) -> tuple[bool, str]:
        """Switch the continuous bed to another theme, live (no restart).

        A control-plane action, not a domain concept: it re-skins the audio
        adapter's loop bed while the session's musical state is untouched.
        Returns (ok, message) for the HTTP/menu callers to surface.
        """
        from ..adapters.mixer.stem_pack import THEMES, ensure_assets

        if theme not in THEMES:
            return False, f"unknown theme '{theme}' (choose: {', '.join(THEMES)})"
        if theme == self._theme:
            return True, f"theme already '{theme}'"
        swap = getattr(self.mixer, "set_stems", None)
        if swap is None:
            return False, "this audio engine can't switch themes live"
        try:
            stems_dir = ensure_assets(self._config.assets_dir, theme, self._log)
            swap(stems_dir)
        except Exception as exc:
            return False, f"could not switch theme: {exc}"
        self._theme = theme
        # set_stems reloaded the new theme's *default* pad; re-apply the chosen
        # ambience so a theme switch keeps the selected pad style.
        self._apply_pad(self._pad_style)
        self._log(f"audio: theme -> '{theme}'")
        return True, f"theme '{theme}'"

    def _apply_pad(self, style: str) -> bool:
        """Synthesize the pad for the current theme+style and swap it in. True if applied."""
        from ..adapters.mixer.stem_pack import pad_buffer

        swap = getattr(self.mixer, "set_loop", None)
        if swap is None:
            return False
        swap("pad", pad_buffer(self._theme, style))
        return True

    def set_pad_style(self, style: str) -> tuple[bool, str]:
        """Switch the ambient pad texture, live. A control-plane action.

        The pad is the sustained bed; its style (e.g. 'low_warm', 'airy') is
        orthogonal to the theme's key. Returns (ok, message).
        """
        from ..adapters.mixer.stem_pack import PAD_STYLES

        if style not in PAD_STYLES:
            return False, f"unknown ambience '{style}' (choose: {', '.join(PAD_STYLES)})"
        if not self._apply_pad(style):
            return False, "this audio engine can't change ambience live"
        self._pad_style = style
        self._log(f"audio: ambience -> '{style}'")
        return True, f"ambience '{style}'"

    def set_voice(self, voice: str | None) -> tuple[bool, str]:
        """Switch the spoken-alert voice, live. A control-plane action.

        `voice` is a macOS `say` voice name (e.g. "Daniel"); None / "" restores
        the system default. Returns (ok, message).
        """
        swap = getattr(self.announcer, "set_voice", None)
        if swap is None:
            return False, "speech is disabled — nothing to configure"
        voice = voice or None
        swap(voice)
        self._voice = voice
        label = voice or "system default"
        self._log(f"speech: voice -> {label}")
        return True, f"voice '{label}'"

    def state_snapshot(self) -> dict:
        """A read-only view of the current musical state + theme/voice (for /state)."""
        from ..adapters.mixer.stem_pack import PAD_STYLES, THEMES

        st = self.session.current()
        return {
            "intent": st.intent.value,
            "intensity": round(st.intensity, 3),
            "anxiety": round(st.anxiety, 3),
            "health": round(st.health, 3),
            "theme": self._theme,
            "themes": list(THEMES),
            "voice": self._voice,
            "pad_style": self._pad_style,
            "pad_styles": list(PAD_STYLES),
        }

    def shutdown(self) -> None:
        self.mixer.shutdown()
        self.session_log.close()
