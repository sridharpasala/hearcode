"""Layer 4 — installs/uninstalls HearCode hooks into Claude Code settings.

Merges a hooks block into ~/.claude/settings.json so every relevant agent
lifecycle event POSTs its payload to the running daemon. Uses curl (no Python
startup cost on the hot path) with a short timeout, so a stopped daemon never
slows the agent — a refused localhost connection fails instantly.
"""

from __future__ import annotations

import json
from pathlib import Path

_MARKER = "127.0.0.1:%(port)d/event"
_HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "SubagentStop",
    "Notification",
    "PermissionRequest",
    "PermissionDenied",
    "SessionStart",
)

# Events that do not support a "matcher" field — register them without one.
_NO_MATCHER = frozenset({"Stop"})


def _curl_command(port: int) -> str:
    return (
        f"curl -sf --max-time 0.25 -X POST "
        f"http://127.0.0.1:{port}/event "
        f"--data-binary @- >/dev/null 2>&1 || true"
    )


def _hook_block(port: int) -> dict:
    command = {"type": "command", "command": _curl_command(port)}
    block: dict = {}
    for event in _HOOK_EVENTS:
        entry = {"hooks": [command]}
        if event not in _NO_MATCHER:
            entry = {"matcher": "*", **entry}
        block[event] = [entry]
    return block


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def install(port: int, path: Path | None = None) -> Path:
    path = path or settings_path()
    settings = json.loads(path.read_text()) if path.exists() else {}
    if path.exists():
        path.with_suffix(".json.hearcode-backup").write_text(json.dumps(settings, indent=2))

    settings.setdefault("hooks", {})
    for event, entries in _hook_block(port).items():
        existing = [
            e
            for e in settings["hooks"].get(event, [])
            if _MARKER % {"port": port} not in json.dumps(e)
        ]
        settings["hooks"][event] = existing + entries

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path


def uninstall(port: int, path: Path | None = None) -> Path:
    path = path or settings_path()
    if not path.exists():
        return path
    settings = json.loads(path.read_text())
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        hooks[event] = [
            e for e in hooks[event] if _MARKER % {"port": port} not in json.dumps(e)
        ]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return path
