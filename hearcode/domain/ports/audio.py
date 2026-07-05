"""Layer 1b — the audio port.

The domain declares *what it needs from an audio engine* in its own language:
"render this mood" and "play this accent." It says nothing about stems, gains,
sample rates, sounddevice, or pygame — those are adapter details. Any engine
that can satisfy this contract (real speakers, a null engine, a future web-audio
engine) is swappable without touching the domain.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.intent import Intent
from ..entities.musical_state import MusicalState


class IAudioMixer(ABC):
    """Contract for the thing that turns musical decisions into sound."""

    @abstractmethod
    def render(self, state: MusicalState) -> None:
        """Move the continuous soundtrack toward the given mood (crossfade)."""

    @abstractmethod
    def accent(self, intent: Intent) -> None:
        """Play a transient one-shot for a moment (e.g. error sting, resolve)."""

    @abstractmethod
    def motif(self, tool: str | None) -> None:
        """Play the short signature 'leitmotif' for a given tool.

        Lets a listener recognise *which* tool the agent just used by ear. The
        tool->sound mapping is an arrangement detail owned by the adapter; the
        domain only names the tool.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """Stop playback and release the audio device."""
