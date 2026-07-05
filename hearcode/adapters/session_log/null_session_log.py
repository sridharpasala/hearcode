"""Layer 3 — the Null Object session log (recording disabled)."""

from __future__ import annotations

from ...domain.entities.session_entry import SessionEntry
from ...domain.ports.session_log import ISessionLog


class NullSessionLog(ISessionLog):
    def record(self, entry: SessionEntry) -> None:
        pass
