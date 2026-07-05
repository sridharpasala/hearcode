"""Layer 4 — configuration (the only place that reads the environment)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 8420


def _clamp01(raw: str | None, default: float) -> float:
    """Parse an env value as a 0..1 float, falling back to `default` if unset/bad."""
    if not raw:
        return default
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return default

# User-writable home for generated assets and logs (works for a pip-installed
# package, where the install dir is read-only / has no bundled WAVs).
HEARCODE_HOME = Path.home() / ".hearcode"
ASSETS_DIR = HEARCODE_HOME / "assets" / "loops"
SESSIONS_DIR = HEARCODE_HOME / "sessions"


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    assets_dir: Path = ASSETS_DIR
    theme: str = "focus"       # stem-pack flavour: "focus" (Cm) or "uplift" (Eb major)
    pad_style: str = "low_warm"  # ambient pad texture (see stem_pack.PAD_STYLES)
    sessions_dir: Path = SESSIONS_DIR
    fade_seconds: float = 0.7
    volume: float = 0.9        # master output ceiling (0..1) — caps overall loudness
    idle_after_seconds: float = 20.0
    idle_poll_seconds: float = 3.0
    window_seconds: float = 10.0
    saturation: int = 8
    silent: bool = False       # force the NullMixer (no audio device)
    leitmotifs: bool = True    # play a per-tool signature on each tool call
    announce: bool = True      # speak "agent needs you" alerts via TTS (macOS)
    voice: str | None = None   # optional `say` voice name
    record: bool = True        # record the session timeline for recaps

    @property
    def stems_dir(self) -> Path:
        """The stem pack actually loaded — the selected theme's subdir."""
        return self.assets_dir / self.theme

    @staticmethod
    def load() -> "Config":
        assets = os.environ.get("HEARCODE_ASSETS")
        return Config(
            port=int(os.environ.get("HEARCODE_PORT", DEFAULT_PORT)),
            assets_dir=Path(assets).expanduser() if assets else ASSETS_DIR,
            theme=os.environ.get("HEARCODE_THEME") or "focus",
            pad_style=os.environ.get("HEARCODE_PAD") or "low_warm",
            volume=_clamp01(os.environ.get("HEARCODE_VOLUME"), 0.9),
            silent=os.environ.get("HEARCODE_SILENT", "") not in ("", "0", "false"),
            leitmotifs=os.environ.get("HEARCODE_LEITMOTIFS", "1") not in ("0", "false"),
            announce=os.environ.get("HEARCODE_ANNOUNCE", "1") not in ("0", "false"),
            voice=os.environ.get("HEARCODE_VOICE") or None,
            record=os.environ.get("HEARCODE_RECORD", "1") not in ("0", "false"),
        )
