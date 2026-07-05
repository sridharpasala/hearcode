"""Layer 3 — the real-time audio adapter (sounddevice + numpy).

Adaptive stem layering, video-game style: every looping stem plays continuously
and stays phase-aligned; we express mood purely by crossfading per-stem gains
toward targets inside the audio callback. One-shot accents (error sting, resolve
chord) are mixed on top and removed when finished.

This is the only file that knows about sample rates, buffers, and gains. It
translates a domain `MusicalState` into "which stems, how loud" via ARRANGEMENT.
Swapping in a different stem pack or a web-audio engine means writing a sibling
adapter — the domain does not change.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from ...domain.entities.intent import Intent
from ...domain.entities.musical_state import MusicalState
from ...domain.ports.audio import IAudioMixer
from .arrangement import ACCENTS, LEITMOTIFS, LOOP_STEMS, MOTIF_FILES, gains_for, read_wav

# Don't retrigger the same tool's motif more often than this (seconds).
_MOTIF_COOLDOWN = 0.18

# Hard ceiling on simultaneously-playing one-shots (accents + motifs). A flood of
# events (malicious or buggy) can't stack an unbounded number of buffers into a
# wall of sound; past the cap the oldest one-shot is dropped so the newest still
# plays. The continuous loop bed is separately bounded by the arrangement gains.
_MAX_ACTIVE_ACCENTS = 6

# Soft-knee limiter threshold: samples below this magnitude pass through
# untouched; louder peaks saturate smoothly toward ±1 (see _soft_limit).
_LIMIT_KNEE = 0.8


def _soft_limit(x: np.ndarray) -> None:
    """In-place soft-knee limiter: transparent below the knee, gentle above.

    Replaces a hard clip so a burst of stacked one-shots rounds off smoothly
    instead of turning into harsh full-scale square-wave clipping. A final hard
    clip stays as a safety net (a no-op in normal operation).
    """
    mag = np.abs(x)
    over = mag > _LIMIT_KNEE
    if over.any():
        head = 1.0 - _LIMIT_KNEE
        x[over] = np.sign(x[over]) * (
            _LIMIT_KNEE + head * np.tanh((mag[over] - _LIMIT_KNEE) / head)
        )
    np.clip(x, -1.0, 1.0, out=x)


class SounddeviceMixer(IAudioMixer):
    def __init__(
        self,
        assets_dir: Path,
        samplerate: int = 44_100,
        blocksize: int = 1024,
        fade_seconds: float = 0.7,
        master: float = 0.9,
        leitmotifs: bool = True,
    ) -> None:
        self._sr = samplerate
        self._master = master
        self._leitmotifs = leitmotifs
        # Per-block gain glide so a crossfade spans ~fade_seconds.
        self._glide = min(1.0, blocksize / max(1, fade_seconds * samplerate))

        self._loops: dict[str, np.ndarray] = {}
        self._accent_buffers: dict[str, np.ndarray] = {}
        self._motif_buffers: dict[str, np.ndarray] = {}
        self._motif_last: dict[str, float] = {}
        self._load_assets(Path(assets_dir))

        # Shared playback state (read in the audio thread, written from main).
        self._lock = threading.Lock()
        self._gain = {name: 0.0 for name in self._loops}      # current
        self._target = {name: 0.0 for name in self._loops}    # desired
        self._pos = {name: 0 for name in self._loops}         # loop read head
        self._active_accents: list[list] = []                 # [buffer, position]

        self._stream = sd.OutputStream(
            samplerate=samplerate,
            blocksize=blocksize,
            channels=2,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    # ---- IAudioMixer -----------------------------------------------------

    def render(self, state: MusicalState) -> None:
        targets = gains_for(state)
        with self._lock:
            for name in self._loops:
                self._target[name] = targets.get(name, 0.0)

    def accent(self, intent: Intent) -> None:
        name = ACCENTS.get(intent)
        buf = self._accent_buffers.get(name) if name else None
        if buf is None:
            return
        with self._lock:
            self._push_accent(buf)

    def motif(self, tool: str | None) -> None:
        if not self._leitmotifs or not tool:
            return
        name = LEITMOTIFS.get(tool)
        buf = self._motif_buffers.get(name) if name else None
        if buf is None:
            return
        now = time.monotonic()
        if now - self._motif_last.get(name, 0.0) < _MOTIF_COOLDOWN:
            return  # same tool fired again too soon — keep it musical
        self._motif_last[name] = now
        with self._lock:
            self._push_accent(buf)

    def _push_accent(self, buf: np.ndarray) -> None:
        """Queue a one-shot, dropping the oldest if the active cap is reached.

        Caller must hold self._lock.
        """
        if len(self._active_accents) >= _MAX_ACTIVE_ACCENTS:
            del self._active_accents[0]  # drop the oldest so the newest still fires
        self._active_accents.append([buf, 0])

    def set_stems(self, stems_dir: Path) -> None:
        """Swap the continuous loop bed to a different theme's stems, in place.

        Reloads the looping stems from `stems_dir` and swaps the buffers under
        the audio lock, preserving each loop's current gain and read position so
        the crossfade and phase carry on uninterrupted — a theme change is
        seamless, with no restart and no silence gap. One-shot accents and
        leitmotifs are theme-independent, so they're left untouched.
        """
        stems_dir = Path(stems_dir)
        fresh: dict[str, np.ndarray] = {}
        for name in LOOP_STEMS:
            data = read_wav(stems_dir / f"{name}.wav")
            if data is not None:
                fresh[name] = data
        if not fresh:
            raise RuntimeError(f"no stem assets found in {stems_dir}")
        with self._lock:
            for name, buf in fresh.items():
                self._loops[name] = buf
                # Keep the read head valid if the new loop is a different length.
                self._pos[name] = self._pos.get(name, 0) % len(buf)
                self._gain.setdefault(name, 0.0)
                self._target.setdefault(name, 0.0)

    def set_loop(self, name: str, buffer: np.ndarray) -> None:
        """Swap a single continuous loop (e.g. the pad) for an in-memory buffer.

        Used to change the pad *ambience* live without touching the other stems:
        the buffer replaces one loop under the audio lock, keeping its gain and
        read position so the crossfade and phase carry on seamlessly. Accepts a
        mono or (frames, 2) array.
        """
        buf = np.asarray(buffer, dtype=np.float32)
        if buf.ndim == 1:
            buf = np.column_stack((buf, buf))
        buf = np.ascontiguousarray(buf, dtype=np.float32)
        with self._lock:
            self._loops[name] = buf
            self._pos[name] = self._pos.get(name, 0) % len(buf)
            self._gain.setdefault(name, 0.0)
            self._target.setdefault(name, 0.0)

    def shutdown(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

    # ---- audio thread ----------------------------------------------------

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        mix = np.zeros((frames, 2), dtype=np.float32)
        with self._lock:
            for name, buf in self._loops.items():
                start, end = self._gain[name], self._target[name]
                if start == 0.0 and end == 0.0:
                    self._pos[name] = (self._pos[name] + frames) % len(buf)
                    continue
                new_gain = start + (end - start) * self._glide
                ramp = np.linspace(start, new_gain, frames, dtype=np.float32)
                chunk, self._pos[name] = self._read_loop(buf, self._pos[name], frames)
                mix += chunk * ramp[:, None]
                self._gain[name] = new_gain

            still_active = []
            for entry in self._active_accents:
                buf, pos = entry
                take = min(frames, len(buf) - pos)
                mix[:take] += buf[pos:pos + take]
                entry[1] = pos + take
                if entry[1] < len(buf):
                    still_active.append(entry)
            self._active_accents = still_active

        np.multiply(mix, self._master, out=mix)
        _soft_limit(mix)  # gentle saturation + safety clip, never harsh full-scale
        outdata[:] = mix

    @staticmethod
    def _read_loop(buf: np.ndarray, pos: int, frames: int) -> tuple[np.ndarray, int]:
        n = len(buf)
        end = pos + frames
        if end <= n:
            return buf[pos:end], end % n
        first = buf[pos:]
        rest = frames - len(first)
        return np.concatenate((first, buf[:rest]), axis=0), rest

    # ---- asset loading ---------------------------------------------------

    def _load_assets(self, assets_dir: Path) -> None:
        for name in LOOP_STEMS:
            data = read_wav(assets_dir / f"{name}.wav")
            if data is not None:
                self._loops[name] = data
        for accent_name in ACCENTS.values():
            data = read_wav(assets_dir / f"{accent_name}.wav")
            if data is not None:
                self._accent_buffers[accent_name] = data
        for motif_name in MOTIF_FILES:
            data = read_wav(assets_dir / f"{motif_name}.wav")
            if data is not None:
                self._motif_buffers[motif_name] = data
        if not self._loops:
            raise RuntimeError(
                f"no stem assets found in {assets_dir} — run tools/gen_stems.py"
            )
