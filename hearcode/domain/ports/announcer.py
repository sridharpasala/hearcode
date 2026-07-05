"""Layer 1b — the announcer port.

A second output modality besides music: speaking to the human. The domain only
says "announce this short message"; whether that's macOS `say`, a future
notification-center toast, or nothing at all is an adapter choice.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IAnnouncer(ABC):
    @abstractmethod
    def announce(self, message: str) -> None:
        """Surface a short spoken/auditory message to the human (non-blocking)."""
