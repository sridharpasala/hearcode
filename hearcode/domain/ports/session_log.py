"""Layer 1b — the session log port.

The domain records each musical moment to "somewhere" so a session can be
recapped later. Whether that's a JSONL file, a database, or nothing is an adapter
choice; the domain only appends entries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.session_entry import SessionEntry


class ISessionLog(ABC):
    @abstractmethod
    def record(self, entry: SessionEntry) -> None:
        """Append one moment of the session timeline."""

    def close(self) -> None:
        """Flush/close any open resources (optional)."""
