"""Layer 3 — render a recap into a shareable waveform image (SVG).

The audio recap tells you what the session *sounded* like; this turns the same
mix into a single picture you can post: a waveform whose colour at each instant
is the agent's musical intent (exploring vs building vs erroring), with markers
where the one-shot alerts fired. The colours are sampled straight from the recap
schedule, so the picture is a faithful map of the audio.

Pure numpy + stdlib string building — SVG is just text, so there's no image
library dependency, matching HearCode's "synthesize everything ourselves" ethos.
SVG is vector (scales to any resolution) and opens in any browser; convert to PNG
with `rsvg-convert`/`cairosvg`/a screenshot if a raster is needed.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import numpy as np

# Musical intent -> colour. Hand-picked so the moods read at a glance and the
# "something went wrong" reds pop against the calm blues/greens.
_INTENT_COLORS = {
    "explore": "#38bdf8",      # sky — curious, reading
    "build": "#34d399",        # emerald — productive
    "action": "#fbbf24",       # amber — driving, running
    "tension": "#fb923c",      # orange — risky / long
    "error": "#ef4444",        # red — a failure
    "stuck": "#dc2626",        # deep red — spinning
    "needs_input": "#a78bfa",  # violet — blocked on the human
    "idle": "#475569",         # slate — quiet
    "done": "#22c55e",         # green — resolved
}
_DEFAULT_COLOR = "#64748b"

# One-shot cues worth annotating on the timeline -> (glyph, colour, label).
_CUE_MARKERS = {
    "error": ("✕", "#ef4444", "error"),
    "stuck": ("⚠", "#dc2626", "stuck"),
    "needs_input": ("◆", "#a78bfa", "needs you"),
    "done": ("✓", "#22c55e", "done"),
}

_BG = "#0f172a"
_FG = "#e2e8f0"
_MUTED = "#94a3b8"


class WaveformExporter:
    def __init__(self, width: int = 1200, height: int = 420, bars: int = 600) -> None:
        self._w = width
        self._h = height
        self._bars = bars

    def export(
        self,
        mix: np.ndarray,
        samplerate: int,
        sched: list[tuple[int, dict]],
        out_path: Path,
        seconds: float,
        title: str = "HearCode session",
        stats=None,
    ) -> Path:
        """Write an SVG waveform poster for a rendered recap mix."""
        total = len(mix)
        heights = self._envelope(mix)
        colors = self._bar_colors(sched, total)

        pad = 48
        top = 96
        band_h = 210
        center = top + band_h / 2
        bar_w = (self._w - 2 * pad) / self._bars
        half = band_h / 2

        parts: list[str] = []
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self._w}" '
            f'height="{self._h}" viewBox="0 0 {self._w} {self._h}" '
            f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
        )
        parts.append(f'<rect width="{self._w}" height="{self._h}" fill="{_BG}"/>')

        # Title + subtitle.
        parts.append(
            f'<text x="{pad}" y="46" fill="{_FG}" font-size="28" '
            f'font-weight="700">♪ {escape(title)}</text>'
        )
        subtitle = self._subtitle(stats, seconds)
        parts.append(
            f'<text x="{pad}" y="72" fill="{_MUTED}" font-size="15">'
            f'{escape(subtitle)}</text>'
        )

        # Faint centre line.
        parts.append(
            f'<line x1="{pad}" y1="{center:.1f}" x2="{self._w - pad}" '
            f'y2="{center:.1f}" stroke="#1e293b" stroke-width="1"/>'
        )

        # Mirrored, mood-coloured bars.
        for i in range(self._bars):
            h = float(heights[i])
            if h <= 0.001:
                continue
            x = pad + i * bar_w
            bh = h * half
            parts.append(
                f'<rect x="{x:.2f}" y="{center - bh:.2f}" '
                f'width="{max(bar_w * 0.8, 0.6):.2f}" height="{bh * 2:.2f}" '
                f'rx="0.6" fill="{colors[i]}"/>'
            )

        # Alert markers along the bottom of the band.
        marker_y = top + band_h + 18
        seen_markers: dict[str, str] = {}
        for offset, entry in sched:
            x = pad + (offset / max(1, total - 1)) * (self._w - 2 * pad)
            for cue in entry.get("cues", ()):
                key = cue.split(":", 1)[0]
                mark = _CUE_MARKERS.get(key)
                if not mark:
                    continue
                glyph, color, label = mark
                seen_markers[label] = color
                parts.append(
                    f'<text x="{x:.1f}" y="{marker_y}" fill="{color}" '
                    f'font-size="15" text-anchor="middle">{glyph}</text>'
                )

        # Mood legend (only intents that actually occurred).
        parts.extend(self._legend(sched, seen_markers))

        # Footer brand line.
        parts.append(
            f'<text x="{self._w - pad}" y="{self._h - 18}" fill="{_MUTED}" '
            f'font-size="13" text-anchor="end">generated by HearCode · '
            f'an adaptive soundtrack for coding agents</text>'
        )
        parts.append("</svg>")

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(parts), encoding="utf-8")
        return out_path

    # ---- internals -------------------------------------------------------

    def _envelope(self, mix: np.ndarray) -> np.ndarray:
        """Peak-amplitude envelope, one value per bar, normalised to [0,1]."""
        mono = np.max(np.abs(mix), axis=1) if mix.ndim == 2 else np.abs(mix)
        edges = np.linspace(0, len(mono), self._bars + 1).astype(int)
        out = np.zeros(self._bars, dtype=np.float32)
        for i in range(self._bars):
            a, b = edges[i], edges[i + 1]
            if b > a:
                out[i] = mono[a:b].max()
        peak = float(out.max())
        return out / peak if peak > 0 else out

    def _bar_colors(self, sched: list[tuple[int, dict]], total: int) -> list[str]:
        """The active intent's colour for each bar (step-held between moments)."""
        offsets = np.array([o for o, _ in sched]) if sched else np.array([0])
        intents = [e.get("intent", "idle") for _, e in sched] or ["idle"]
        centers = ((np.arange(self._bars) + 0.5) / self._bars * (total - 1)).astype(int)
        idx = np.clip(np.searchsorted(offsets, centers, side="right") - 1, 0, len(intents) - 1)
        return [_INTENT_COLORS.get(intents[j], _DEFAULT_COLOR) for j in idx]

    def _subtitle(self, stats, seconds: float) -> str:
        if stats is None:
            return f"{seconds:.0f}s recap"
        bits = [f"{stats.moments} moments", f"{stats.duration_seconds:.0f}s of work"]
        if stats.tools:
            top = stats.tools.most_common(1)[0]
            bits.append(f"busiest: {top[0]}×{top[1]}")
        bits.append(f"peak intensity {stats.peak_intensity:.2f}")
        if stats.peak_anxiety > 0.0:
            bits.append(f"peak anxiety {stats.peak_anxiety:.2f}")
        return "   ·   ".join(bits)

    def _legend(self, sched: list[tuple[int, dict]], markers: dict[str, str]) -> list[str]:
        order = list(_INTENT_COLORS)
        present = {e.get("intent", "idle") for _, e in sched}
        items = [(name, _INTENT_COLORS[name]) for name in order if name in present]
        # Add cue-marker labels, but skip any whose word already shows as a mood
        # (error/stuck/done are both an intent colour and a marker glyph).
        shown = {label for label, _ in items}
        items += [(label, color) for label, color in markers.items() if label not in shown]

        parts: list[str] = []
        x = 48
        y = self._h - 18
        for label, color in items:
            parts.append(
                f'<rect x="{x}" y="{y - 11}" width="12" height="12" rx="2" fill="{color}"/>'
            )
            x += 18
            parts.append(
                f'<text x="{x}" y="{y - 1}" fill="{_MUTED}" font-size="13">'
                f'{escape(label.replace("_", " "))}</text>'
            )
            x += 12 + len(label) * 8 + 12
        return parts
