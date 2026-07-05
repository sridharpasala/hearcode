"""Layer 3 — render a recorded session timeline back into a short audio recap.

The live `SounddeviceMixer` streams the soundtrack in real time; this renderer
replays the same decisions *offline* from a session log, time-compressed into a
~30s highlight reel. It shares `arrangement` with the live mixer, so a recap
sounds like a fast-forward of what you actually heard — same stems, same gains,
same accents — never a separate "remix".

Pure numpy + stdlib `wave`: no audio device, so a recap can be produced on a
headless box or long after the session ended.
"""

from __future__ import annotations

import json
import wave
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ...domain.entities.intent import Intent
from ...domain.entities.musical_state import MusicalState
from ..mixer.arrangement import LOOP_STEMS, cue_sample, gains_for, read_wav

_INTENT_BY_VALUE = {i.value: i for i in Intent}


def load_session(path: Path) -> list[dict]:
    """Read one JSONL session log into a list of entry dicts (in order)."""
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def latest_session(sessions_dir: Path) -> Path | None:
    """The most recently started session log in a directory, or None."""
    files = sorted(Path(sessions_dir).glob("*.jsonl"))
    return files[-1] if files else None


@dataclass(frozen=True)
class SessionStats:
    moments: int
    duration_seconds: float
    intents: Counter
    tools: Counter
    cues: Counter
    peak_anxiety: float
    peak_intensity: float
    final_health: float


def session_stats(entries: list[dict]) -> SessionStats:
    """Summarise a session timeline for the printed recap."""
    intents: Counter = Counter()
    tools: Counter = Counter()
    cues: Counter = Counter()
    peak_anx = peak_int = 0.0
    health = 0.5
    for e in entries:
        intents[e.get("intent", "?")] += 1
        if e.get("tool"):
            tools[e["tool"]] += 1
        for cue in e.get("cues", ()):  # motif:Edit, stuck, error, …
            cues[cue.split(":", 1)[0]] += 1
        peak_anx = max(peak_anx, float(e.get("anxiety", 0.0)))
        peak_int = max(peak_int, float(e.get("intensity", 0.0)))
        health = float(e.get("health", health))
    span = 0.0
    if entries:
        span = float(entries[-1].get("at", 0.0)) - float(entries[0].get("at", 0.0))
    return SessionStats(
        moments=len(entries),
        duration_seconds=max(0.0, span),
        intents=intents,
        tools=tools,
        cues=cues,
        peak_anxiety=peak_anx,
        peak_intensity=peak_int,
        final_health=health,
    )


def _state_of(entry: dict) -> MusicalState:
    intent = _INTENT_BY_VALUE.get(entry.get("intent", ""), Intent.IDLE)
    return MusicalState(
        intent=intent,
        intensity=float(entry.get("intensity", 0.0)),
        anxiety=float(entry.get("anxiety", 0.0)),
        health=float(entry.get("health", 0.5)),
    )


def schedule(entries: list[dict], total_samples: int) -> list[tuple[int, dict]]:
    """Map each recorded moment onto a sample offset in a `total_samples` reel.

    Shared by the audio renderer and the waveform exporter so the colours line up
    with the sound exactly.
    """
    t0 = float(entries[0].get("at", 0.0))
    span = float(entries[-1].get("at", 0.0)) - t0
    out: list[tuple[int, dict]] = []
    for e in entries:
        frac = ((float(e.get("at", 0.0)) - t0) / span) if span > 0 else 0.0
        offset = int(min(max(frac, 0.0), 1.0) * max(0, total_samples - 1))
        out.append((offset, e))
    return out


class RecapRenderer:
    """Replays a session log into a compressed stereo WAV highlight reel."""

    def __init__(
        self,
        assets_dir: Path,
        samplerate: int = 44_100,
        blocksize: int = 1024,
        fade_seconds: float = 0.5,
        master: float = 0.9,
    ) -> None:
        self._sr = samplerate
        self._block = blocksize
        self._master = master
        self._glide = min(1.0, blocksize / max(1, fade_seconds * samplerate))
        self._loops: dict[str, np.ndarray] = {}
        for name in LOOP_STEMS:
            data = read_wav(Path(assets_dir) / f"{name}.wav")
            if data is not None:
                self._loops[name] = data
        self._assets_dir = Path(assets_dir)
        self._cue_cache: dict[str, np.ndarray | None] = {}
        if not self._loops:
            raise RuntimeError(
                f"no stem assets found in {assets_dir} — run tools/gen_stems.py"
            )

    @property
    def samplerate(self) -> int:
        return self._sr

    def mix_for(
        self, entries: list[dict], seconds: float = 30.0
    ) -> tuple[np.ndarray, list[tuple[int, dict]]]:
        """Render `entries` to a stereo float32 mix + the sample-offset schedule.

        Returned so a caller can both write the WAV and draw the matching
        waveform without rendering the audio twice.
        """
        if not entries:
            raise ValueError("empty session — nothing to recap")

        total = int(seconds * self._sr)
        mix = np.zeros((total, 2), dtype=np.float32)
        sched = schedule(entries, total)

        # Continuous stem bed: glide gains toward the active moment's targets,
        # block by block, exactly like the live callback does.
        gain = {name: 0.0 for name in self._loops}
        target = {name: 0.0 for name in self._loops}
        pos = {name: 0 for name in self._loops}
        idx = 0
        for start in range(0, total, self._block):
            frames = min(self._block, total - start)
            while idx < len(sched) and sched[idx][0] <= start:
                targets = gains_for(_state_of(sched[idx][1]))
                for name in self._loops:
                    target[name] = targets.get(name, 0.0)
                idx += 1
            for name, buf in self._loops.items():
                s, end = gain[name], target[name]
                if s == 0.0 and end == 0.0:
                    pos[name] = (pos[name] + frames) % len(buf)
                    continue
                new_gain = s + (end - s) * self._glide
                ramp = np.linspace(s, new_gain, frames, dtype=np.float32)
                chunk, pos[name] = self._read_loop(buf, pos[name], frames)
                mix[start:start + frames] += chunk * ramp[:, None]
                gain[name] = new_gain

        # Overlay one-shot accents / motifs at each moment's offset.
        for offset, entry in sched:
            for cue in entry.get("cues", ()):
                buf = self._cue_buffer(cue)
                if buf is None:
                    continue
                take = min(len(buf), total - offset)
                if take > 0:
                    mix[offset:offset + take] += buf[:take]

        np.multiply(mix, self._master, out=mix)
        np.clip(mix, -1.0, 1.0, out=mix)
        return mix, sched

    def render(self, entries: list[dict], out_path: Path, seconds: float = 30.0) -> Path:
        """Render `entries` into a `seconds`-long WAV at `out_path`."""
        mix, _sched = self.mix_for(entries, seconds)
        self.write_wav(out_path, mix)
        return Path(out_path)

    def _cue_buffer(self, cue: str) -> np.ndarray | None:
        if cue not in self._cue_cache:
            name = cue_sample(cue)
            self._cue_cache[cue] = (
                read_wav(self._assets_dir / f"{name}.wav") if name else None
            )
        return self._cue_cache[cue]

    @staticmethod
    def _read_loop(buf: np.ndarray, pos: int, frames: int) -> tuple[np.ndarray, int]:
        n = len(buf)
        end = pos + frames
        if end <= n:
            return buf[pos:end], end % n
        first = buf[pos:]
        rest = frames - len(first)
        return np.concatenate((first, buf[:rest]), axis=0), rest

    def write_wav(self, out_path: Path, mix: np.ndarray) -> None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(mix, -1.0, 1.0) * 32767.0).astype(np.int16)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(self._sr)
            wf.writeframes(pcm.tobytes())
