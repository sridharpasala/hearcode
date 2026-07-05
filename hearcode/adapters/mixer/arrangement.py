"""Layer 3 (shared) — the stem arrangement, asset loading, and cue mapping.

Pure numpy + stdlib, no audio device: this is the knowledge of *how a domain
MusicalState becomes concrete stem gains* and *which sample a cue maps to*. Both
the live `SounddeviceMixer` and the offline recap renderer use it, so the
soundtrack sounds identical whether it's streamed live or rendered to a file.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from ...domain.entities.intent import Intent
from ...domain.entities.musical_state import MusicalState

# Continuously-looping stems (filename stem -> role).
LOOP_STEMS = ("pad", "bass", "drums", "lead", "tension", "harmony_bright", "harmony_dark")

# One-shot accents keyed by intent.
ACCENTS = {
    Intent.ERROR: "error_sting",
    Intent.DONE: "resolve",
    Intent.STUCK: "stuck_alert",
    Intent.NEEDS_INPUT: "needs_you",
}

# Per-tool leitmotifs: tool name -> motif sample. Several tools share a family so
# the ear learns "searching", "writing", "running" rather than 20 separate cues.
LEITMOTIFS = {
    "Read": "motif_read", "NotebookRead": "motif_read",
    "Grep": "motif_search", "Glob": "motif_search", "LS": "motif_search",
    "ToolSearch": "motif_search",
    "Edit": "motif_edit", "Write": "motif_edit", "MultiEdit": "motif_edit",
    "NotebookEdit": "motif_edit", "Update": "motif_edit", "ApplyPatch": "motif_edit",
    "Bash": "motif_bash",
    "WebFetch": "motif_web", "WebSearch": "motif_web",
    "Task": "motif_agent", "Agent": "motif_agent", "Skill": "motif_agent",
    "Workflow": "motif_agent",
}
MOTIF_FILES = frozenset(LEITMOTIFS.values())

# Rhythmic stems whose loudness scales with intensity.
_RHYTHMIC = frozenset({"bass", "drums", "lead"})

# intent -> base gain per stem (0 == silent). The "arrangement".
ARRANGEMENT: dict[Intent, dict[str, float]] = {
    Intent.EXPLORE: {"pad": 0.70},
    Intent.BUILD:   {"pad": 0.45, "bass": 0.60, "drums": 0.50},
    Intent.ACTION:  {"pad": 0.35, "bass": 0.60, "drums": 0.75, "lead": 0.60},
    Intent.TENSION: {"pad": 0.40, "tension": 0.70, "drums": 0.40},
    Intent.ERROR:   {"pad": 0.40, "tension": 0.60},
    Intent.IDLE:    {},  # silent — no ambient bed drones between sessions
    Intent.DONE:    {},  # everything fades out; the resolve accent carries the end
}

# Moods with no continuous soundtrack: the music is silent and only returns when
# activity resumes. The health/anxiety colour overlays don't apply to them either.
_SILENT_INTENTS = frozenset({Intent.IDLE, Intent.DONE})

# Cue strings (as recorded in the session log) -> non-motif accent sample names.
_CUE_SAMPLES = {
    "error": "error_sting",
    "done": "resolve",
    "stuck": "stuck_alert",
    "needs_input": "needs_you",
}


def gains_for(state: MusicalState) -> dict[str, float]:
    """Target gain per loop stem for a MusicalState (the core arrangement rule)."""
    base = ARRANGEMENT.get(state.intent, {})
    scaled: dict[str, float] = {}
    for name, gain in base.items():
        if name in _RHYTHMIC:
            gain *= 0.55 + 0.45 * state.intensity  # busier work => louder groove
        scaled[name] = gain
    # When the agent is idle or done, the soundtrack falls fully silent — no
    # ambient pad or health-harmony bed lingers after a turn. The mood (and its
    # anxiety/health colour) returns the instant activity resumes.
    if state.intent in _SILENT_INTENTS:
        return scaled
    # Stuck-loop unease: bleed the dissonant tension drone in over *any* mood.
    if state.anxiety > 0.0:
        scaled["tension"] = max(scaled.get("tension", 0.0), 0.2 + 0.6 * state.anxiety)
    # Build-health harmony: brighten when green, darken when red; neutral plays neither.
    bright = max(0.0, (state.health - 0.5) * 2.0)
    dark = max(0.0, (0.5 - state.health) * 2.0)
    if bright > 0.01:
        scaled["harmony_bright"] = 0.12 + 0.4 * bright
    if dark > 0.01:
        scaled["harmony_dark"] = 0.12 + 0.4 * dark
    return scaled


def cue_sample(cue: str) -> str | None:
    """Map a recorded cue string to a sample name (for offline recap)."""
    if cue.startswith("motif:"):
        return LEITMOTIFS.get(cue.split(":", 1)[1])
    return _CUE_SAMPLES.get(cue)


def read_wav(path: Path) -> np.ndarray | None:
    """Load a 16-bit WAV as a contiguous float32 stereo array, or None if absent."""
    if not path.exists():
        return None
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        raw = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        channels = wf.getnchannels()
    stereo = np.column_stack((raw, raw)) if channels == 1 else raw.reshape(-1, 2)
    return np.ascontiguousarray(stereo, dtype=np.float32)
