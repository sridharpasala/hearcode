"""Layer 3 — append the session timeline to a JSONL file.

One file per Claude session: a new file is started whenever a `session_start`
event arrives. Each line is one SessionEntry plus a wall-clock stamp. Writes are
flushed so a recap works even while the daemon is still running.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from ...domain.entities.session_entry import SessionEntry
from ...domain.ports.session_log import ISessionLog


class JsonlSessionLog(ISessionLog):
    def __init__(self, sessions_dir: Path) -> None:
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._path: Path | None = None

    def record(self, entry: SessionEntry) -> None:
        if self._file is None or entry.kind == "session_start":
            self._rotate()
        row = asdict(entry)
        row["cues"] = list(entry.cues)
        row["wall"] = time.time()
        self._file.write(json.dumps(row) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def _rotate(self) -> None:
        self.close()
        self._path = self._dir / (time.strftime("%Y%m%d-%H%M%S") + ".jsonl")
        self._file = open(self._path, "a", encoding="utf-8")

    @property
    def path(self) -> Path | None:
        return self._path
