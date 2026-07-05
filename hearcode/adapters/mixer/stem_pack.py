"""Layer 3 — the stem-pack synthesizer (numpy + stdlib, no audio device).

Synthesizes a royalty-free, seamless looping stem pack so HearCode is audible
with zero asset sourcing or downloads. Everything is built around C minor at
120 BPM over a 4-bar (8s) loop, so the layers stay in key and phase-aligned; the
"uplift" theme reskins the mood bed in Eb major (C minor's relative major) over
the same grid.

This lives in the package (not a dev script) so a fresh `pip install` can build
its own pack into a user-writable dir on first run — `ensure_assets()`. No WAVs
are shipped in the wheel. Replace these WAVs with real loops at the same
length/key to upgrade the sound — the engine doesn't change.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44_100
BPM = 120
BEATS = 16                      # 4 bars * 4 beats
SECONDS = BEATS * 60 / BPM      # 8.0s
N = int(SR * SECONDS)

# C minor-ish frequencies (Hz).
C2, C3, EB3, G3, C4, EB4, G4, C5 = 65.41, 130.81, 155.56, 196.00, 261.63, 311.13, 392.00, 523.25
C6 = 1046.50
BB4, D5 = 466.16, 587.33   # for the bright (Eb-major) harmony shimmer
GB2 = 92.50                # low tritone for the dark (red-build) drone
G2 = 98.00                 # low fifth for the "low & warm" pad ambience
FS3 = 185.00  # tritone for tension
# Eb-major notes (Hz) for the "uplift" theme — the relative major of C minor,
# so it shares the same key signature as everything above and stays in key.
EB2, BB2, BB3, EB5 = 77.78, 116.54, 233.08, 622.25


def _t(n: int = N) -> np.ndarray:
    return np.arange(n) / SR


def _sine(freq: float, n: int = N, phase: float = 0.0) -> np.ndarray:
    return np.sin(2 * np.pi * freq * _t(n) + phase)


def _detuned(freq: float, cents: float = 6.0) -> np.ndarray:
    """Two sines a few cents apart — a slow warm chorus instead of a sterile tone."""
    ratio = 2 ** (cents / 1200.0)
    return 0.5 * (_sine(freq / ratio) + _sine(freq * ratio))


def _seamless(buf: np.ndarray, fade_s: float = 0.05) -> np.ndarray:
    """Crossfade the tail into the head so the loop has no click."""
    f = int(SR * fade_s)
    if f * 2 >= len(buf):
        return buf
    head, tail = buf[:f].copy(), buf[-f:]
    ramp = np.linspace(0.0, 1.0, f)
    out = buf[:-f].copy()
    out[:f] = head * ramp + tail * (1.0 - ramp)
    return out


def _beat_envelope(hits, attack=0.005, decay=0.18) -> np.ndarray:
    """Percussive amplitude envelope with a hit at each beat index in `hits`."""
    env = np.zeros(N)
    spb = N / BEATS
    a, d = int(SR * attack), int(SR * decay)
    for b in hits:
        start = int(b * spb)
        up = min(a, N - start)
        env[start:start + up] += np.linspace(0, 1, up)
        down = min(d, N - start - up)
        if down > 0:
            s = start + up
            env[s:s + down] += np.linspace(1, 0, down)
    return np.clip(env, 0, 1)


# ---- pad ambience styles -------------------------------------------------
# The pad is the sustained bed under everything. Its *texture* is selectable
# ("ambience") independently of the theme: each style is a function of a theme's
# chord voicing (root/third/fifth/…), so it stays in key in both focus (C-minor)
# and uplift (Eb-major). Styles range from present (classic) to nearly invisible
# (airy). The default is "low_warm" — the least distracting for long sessions.

# Per-theme pad voicing: the chord tones each ambience style draws from.
PAD_VOICINGS: dict[str, dict[str, float]] = {
    "focus":  {"root": C3, "third": EB3, "fifth": G3, "octave": C4,
               "low_root": C2, "low_fifth": G2},
    "uplift": {"root": EB3, "third": G3, "fifth": BB3, "octave": EB4,
               "low_root": EB2, "low_fifth": BB2},
}


def _pad_classic(v: dict) -> np.ndarray:
    # Full triad, pure sines, a slow tremolo — the original, most "present" bed.
    chord = _sine(v["root"]) + _sine(v["third"]) + _sine(v["fifth"]) + 0.6 * _sine(v["octave"])
    tremolo = 0.85 + 0.15 * _sine(0.2)
    return _seamless(chord * tremolo / 3.0)


def _pad_open_fifths(v: dict) -> np.ndarray:
    # Drop the third — root/fifth/octave only. Spacious and neutral; a much
    # subtler, slower swell than classic.
    chord = _sine(v["root"]) + _sine(v["fifth"]) + 0.6 * _sine(v["octave"])
    tremolo = 0.94 + 0.06 * _sine(0.1)
    return _seamless(_peak(chord * tremolo, 0.42))


def _pad_low_warm(v: dict) -> np.ndarray:
    # An octave down, detuned for warmth, no pulsing — sits *under* the work.
    chord = _detuned(v["low_root"]) + 0.7 * _detuned(v["low_fifth"]) + 0.6 * _detuned(v["root"])
    return _seamless(_peak(chord, 0.5))


def _pad_detuned_soft(v: dict) -> np.ndarray:
    # Keeps the triad's colour (minor/major per theme) but warm and still.
    chord = (_detuned(v["root"]) + 0.8 * _detuned(v["third"])
             + 0.8 * _detuned(v["fifth"]) + 0.4 * _sine(v["octave"]))
    return _seamless(_peak(chord, 0.4))


def _pad_airy(v: dict) -> np.ndarray:
    # Just root+fifth, quiet, with a barely-there swell — the most invisible.
    chord = _detuned(v["root"]) + 0.6 * _detuned(v["fifth"])
    swell = 0.97 + 0.03 * _sine(0.05)
    return _seamless(_peak(chord * swell, 0.34))


# Ordered most-invisible-first (how the menu lists them); the first is the default.
PAD_STYLES = {
    "low_warm": _pad_low_warm,
    "open_fifths": _pad_open_fifths,
    "detuned_soft": _pad_detuned_soft,
    "airy": _pad_airy,
    "classic": _pad_classic,
}
DEFAULT_PAD_STYLE = "low_warm"


def pad_buffer(theme: str, style: str) -> np.ndarray:
    """Synthesize the pad bed for a theme in the given ambience style (mono)."""
    voicing = PAD_VOICINGS.get(theme, PAD_VOICINGS["focus"])
    fn = PAD_STYLES.get(style, PAD_STYLES[DEFAULT_PAD_STYLE])
    return fn(voicing)


# ---- "focus" theme bed — the original C-minor, kick-driven groove --------

def pad() -> np.ndarray:
    # The on-disk pad is the default ambience; the live pad is synthesized from
    # the chosen style at startup (see Container), so this is the fallback bed.
    return pad_buffer("focus", DEFAULT_PAD_STYLE)


def bass() -> np.ndarray:
    env = _beat_envelope(range(0, BEATS, 2), decay=0.22)
    tone = _sine(C2) + 0.4 * _sine(C2 * 2)
    return _seamless(tone * env * 0.9)


def drums() -> np.ndarray:
    # Kick on the beat, hat on the off-beat.
    kick_env = _beat_envelope(range(BEATS), decay=0.12)
    pitch = 110 * np.exp(-6 * (_t() % (SECONDS / BEATS)))   # quick downward chirp
    kick = np.sin(2 * np.pi * np.cumsum(pitch) / SR) * kick_env
    rng = np.random.default_rng(7)
    hat_env = _beat_envelope([b + 0.5 for b in range(BEATS)], attack=0.001, decay=0.04)
    hat = rng.standard_normal(N) * hat_env * 0.3
    return _seamless(kick * 0.9 + hat)


def lead() -> np.ndarray:
    notes = [C4, EB4, G4, C5, G4, EB4, C4, EB4]   # arpeggio, two per bar-ish
    env = _beat_envelope(range(BEATS), attack=0.004, decay=0.16)
    spb = N / BEATS
    sig = np.zeros(N)
    for i in range(BEATS):
        start = int(i * spb)
        end = int((i + 1) * spb)
        freq = notes[i % len(notes)]
        seg = _sine(freq, end - start)
        sig[start:end] += seg
    return _seamless(sig * env * 0.5)


# ---- "uplift" theme bed — bright Eb-major, shaker groove ----------------
# Same stem *names* (pad/bass/drums/lead) as the focus bed, so the arrangement
# and every overlay work unchanged — only the character of the bed changes.

def pad_uplift() -> np.ndarray:
    # The uplift bed's default ambience (Eb-major voicing). Like the focus pad,
    # the live pad is re-synthesized from the selected style at startup.
    return pad_buffer("uplift", DEFAULT_PAD_STYLE)


def bass_uplift() -> np.ndarray:
    # Light Eb–Bb bounce — gives the sunny bed forward motion, not a heavy drone.
    pattern = {0: EB2, 2: BB2, 4: EB2, 6: BB2, 8: EB2, 10: BB2, 12: EB2, 14: BB2}
    spb = N / BEATS
    sig = np.zeros(N)
    for beat, freq in pattern.items():
        start = int(beat * spb)
        seg_t = _t(int(spb))
        seg = (np.sin(2 * np.pi * freq * seg_t) + 0.4 * np.sin(2 * np.pi * freq * 2 * seg_t))
        sig[start:start + len(seg)] += seg * np.exp(-seg_t / 0.18)
    return _seamless(sig * 0.8)


def drums_shaker() -> np.ndarray:
    # "Good vibes" groove: shaker on the 8ths, handclap on the backbeat, light kick.
    rng = np.random.default_rng(11)
    shaker_env = _beat_envelope([i * 0.5 for i in range(BEATS * 2)], attack=0.001, decay=0.05)
    shaker = np.diff(rng.standard_normal(N) * shaker_env * 0.18, prepend=0.0)  # diff = bright "tss"
    clap_env = _beat_envelope([b for b in range(BEATS) if b % 2 == 1], attack=0.002, decay=0.12)
    clap = np.diff(rng.standard_normal(N) * clap_env * 0.35, prepend=0.0)      # backbeat (2 & 4)
    kick_env = _beat_envelope(range(0, BEATS, 4), decay=0.12)                  # downbeat only — airy
    pitch = 90 * np.exp(-7 * (_t() % (SECONDS / BEATS)))
    kick = np.sin(2 * np.pi * np.cumsum(pitch) / SR) * kick_env * 0.6
    return _seamless(shaker + clap + kick)


def lead_uplift() -> np.ndarray:
    # Rising Eb-major arpeggio, marimba-bright — "things are clicking".
    notes = [EB4, G4, BB4, EB5, BB4, G4, BB4, G4]
    env = _beat_envelope(range(BEATS), attack=0.003, decay=0.14)
    spb = N / BEATS
    sig = np.zeros(N)
    for i in range(BEATS):
        start = int(i * spb)
        seg_t = _t(int(spb))
        freq = notes[i % len(notes)]
        seg = np.sin(2 * np.pi * freq * seg_t) + 0.25 * np.sin(2 * np.pi * freq * 4 * seg_t)
        sig[start:start + len(seg)] += seg
    return _seamless(sig * env * 0.45)


# ---- shared overlays / alerts (theme-independent) ------------------------

def tension() -> np.ndarray:
    drone = _sine(C3) + _sine(FS3)              # dissonant tritone
    wobble = 0.7 + 0.3 * _sine(0.7)
    return _seamless(drone * wobble * 0.35)


def harmony_bright() -> np.ndarray:
    # Bright Eb-major shimmer (the relative major of C minor) — "green build".
    chord = _sine(EB4) + _sine(G4) + _sine(BB4) + 0.5 * _sine(D5)
    shimmer = 0.82 + 0.18 * _sine(0.25)
    return _seamless(chord * shimmer / 3.5 * 0.7)


def harmony_dark() -> np.ndarray:
    # Low tritone dread drone — "red build".
    drone = _sine(C2) + _sine(GB2) + 0.5 * _sine(C3)
    swell = 0.7 + 0.3 * _sine(0.15)
    return _seamless(drone * swell * 0.5)


def error_sting() -> np.ndarray:
    n = int(SR * 0.5)
    sweep = np.linspace(330, 160, n)
    tone = np.sin(2 * np.pi * np.cumsum(sweep) / SR)
    tone += 0.5 * np.sin(2 * np.pi * np.cumsum(sweep * 1.06) / SR)  # beating/detune
    env = np.linspace(1, 0, n) ** 1.5
    return tone * env * 0.6


def resolve() -> np.ndarray:
    n = int(SR * 1.3)
    t = np.arange(n) / SR
    chord = np.zeros(n)
    for i, f in enumerate((C4, EB4, G4, C5)):       # C minor -> bright resolve
        onset = int(i * 0.06 * SR)
        e = np.zeros(n)
        e[onset:] = np.linspace(1, 0, n - onset) ** 1.2
        chord += np.sin(2 * np.pi * f * t) * e
    return chord / 4.0 * 0.8


# ---- per-tool leitmotifs (short, in-key signatures) ----------------------

def needs_you() -> np.ndarray:
    # Soft two-note bell — a gentle "come back" nudge, not an alarm. One phrase
    # (no repeat), a warmer/lower register, softened partials and attack, and a
    # level below the default accent so it sits under the music rather than over it.
    def bell(freq, dur):
        return _note(freq, dur, partials=(1, 2.0), amps=(1, 0.22),
                     attack=0.012, decay=dur * 0.6)

    G5, C6 = 783.99, 1046.50            # gentle rising fourth — clear but soft
    phrase = np.concatenate([bell(G5, 0.24), bell(C6, 0.55)])
    return _peak(phrase, 0.32)          # subtler than the old double chime (was 0.6)


def stuck_alert() -> np.ndarray:
    # Anxious, wavering dissonant dyad that creeps upward — "you're spinning".
    n = int(SR * 0.8)
    t = np.arange(n) / SR
    vib = 1 + 0.03 * np.sin(2 * np.pi * 7 * t)      # nervous vibrato
    rise = 1 + 0.18 * (t / 0.8)                     # slow creep upward
    a = np.sin(2 * np.pi * C5 * vib * rise * t)
    b = np.sin(2 * np.pi * C5 * 1.06 * vib * rise * t)  # minor-2nd beating (tense)
    tremolo = 0.7 + 0.3 * np.sin(2 * np.pi * 9 * t)     # fluttering pulse
    env = np.minimum(np.linspace(0, 1, n) * 6, 1.0) * np.linspace(1, 0, n) ** 0.6
    return _peak((a + b) * tremolo * env, 0.4)


def _note(freq, dur, partials=(1.0,), amps=(1.0,), attack=0.005, decay=None):
    """One enveloped tone with optional harmonic partials."""
    n = int(SR * dur)
    t = np.arange(n) / SR
    sig = sum(a * np.sin(2 * np.pi * freq * p * t) for p, a in zip(partials, amps))
    env = np.exp(-t / (decay or dur * 0.5))
    a = int(SR * attack)
    if a:
        env[:a] *= np.linspace(0, 1, a)
    return sig * env


def _peak(sig, level=0.4):
    m = np.max(np.abs(sig)) or 1.0
    return sig / m * level


def motif_read() -> np.ndarray:
    # Soft marimba pluck — calm "looking around".
    return _peak(_note(EB4, 0.40, partials=(1, 4), amps=(1, 0.25), decay=0.12))


def motif_search() -> np.ndarray:
    # Two quick RISING notes — "seeking".
    a = _note(G4, 0.12, partials=(1, 2), amps=(1, 0.3), decay=0.08)
    b = _note(C5, 0.16, partials=(1, 2), amps=(1, 0.3), decay=0.10)
    return _peak(np.concatenate([a, b]))


def motif_edit() -> np.ndarray:
    # Two FALLING piano-ish notes — "putting something down".
    a = _note(C5, 0.16, partials=(1, 2, 3), amps=(1, 0.5, 0.25), decay=0.16)
    b = _note(G4, 0.22, partials=(1, 2, 3), amps=(1, 0.5, 0.25), decay=0.20)
    return _peak(np.concatenate([a, b]), 0.45)


def motif_bash() -> np.ndarray:
    # Percussive tom thump + click — "doing something".
    n = int(SR * 0.25)
    pitch = np.linspace(120, 55, n)
    body = np.sin(2 * np.pi * np.cumsum(pitch) / SR) * np.exp(-np.arange(n) / SR / 0.07)
    rng = np.random.default_rng(3)
    click = rng.standard_normal(n) * np.exp(-np.arange(n) / SR / 0.01) * 0.4
    return _peak(body + click, 0.5)


def motif_web() -> np.ndarray:
    # Bright inharmonic bell — "reaching outside".
    return _peak(_note(C6, 0.5, partials=(1, 2.76, 5.4), amps=(1, 0.5, 0.25), decay=0.28))


def motif_agent() -> np.ndarray:
    # Warm horn swell — "a new voice joins" (subagents / tasks).
    return _peak(
        _note(C4, 0.5, partials=(1, 2, 3, 4, 5), amps=(1, 0.5, 0.33, 0.25, 0.2),
              attack=0.05, decay=0.35),
        0.42,
    )


# The mood bed each *theme* reskins — same stem names, different character.
THEME_BED = {
    "focus":  {"pad": pad, "bass": bass, "drums": drums, "lead": lead},
    "uplift": {"pad": pad_uplift, "bass": bass_uplift,
               "drums": drums_shaker, "lead": lead_uplift},
}
THEMES = tuple(THEME_BED)

# Overlay / alert / leitmotif stems — identical in every theme (they share Eb-major
# and C-minor's key signature, so they stay in key under either bed).
SHARED = {
    "tension": tension, "harmony_bright": harmony_bright, "harmony_dark": harmony_dark,
    "error_sting": error_sting, "resolve": resolve, "stuck_alert": stuck_alert,
    "needs_you": needs_you,
    "motif_read": motif_read, "motif_search": motif_search,
    "motif_edit": motif_edit, "motif_bash": motif_bash,
    "motif_web": motif_web, "motif_agent": motif_agent,
}


def _write(out_dir: Path, name: str, mono: np.ndarray) -> None:
    mono = np.clip(mono, -1.0, 1.0)
    stereo = np.column_stack((mono, mono))
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(str(out_dir / f"{name}.wav"), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def generate(out_dir: Path) -> Path:
    """Synthesize the full stem pack (every theme) under `out_dir/<theme>/`.

    Returns `out_dir`. Idempotent: overwrites whatever is there.
    """
    out_dir = Path(out_dir)
    for theme, bed in THEME_BED.items():
        theme_dir = out_dir / theme
        theme_dir.mkdir(parents=True, exist_ok=True)
        for name, fn in {**SHARED, **bed}.items():
            _write(theme_dir, name, fn())
    return out_dir


def ensure_assets(assets_dir: Path, theme: str = "focus", log=lambda *_: None) -> Path:
    """Make sure the selected theme's stem pack exists, building it on first run.

    Returns the resolved per-theme stems dir (`assets_dir/<theme>`). Cheap to call
    repeatedly: it only synthesizes when the pack is missing.
    """
    assets_dir = Path(assets_dir)
    stems_dir = assets_dir / theme
    if stems_dir.is_dir() and any(stems_dir.glob("*.wav")):
        return stems_dir
    log(f"stems: synthesizing pack into {assets_dir} (first run)…")
    generate(assets_dir)
    return stems_dir
