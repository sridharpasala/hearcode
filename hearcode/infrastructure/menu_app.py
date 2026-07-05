"""Layer 4 — menu bar app lifecycle (detached spawn + stop via a pidfile).

The macOS menu bar app (`hearcode menu`) owns the AppKit run loop and blocks, so
`init` can't just call it inline — it launches it detached the same way the
daemon is: its own session, stdout teed to a log, PID recorded in
`~/.hearcode/menu.pid`. It's optional and macOS-only (needs the `menubar` extra),
so a missing dependency or a non-Mac host is a soft skip, never an error.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import signal
import subprocess
import sys
import time

from .config import HEARCODE_HOME, Config

MENU_PIDFILE = HEARCODE_HOME / "menu.pid"
MENU_LOGFILE = HEARCODE_HOME / "menu.log"


def available() -> tuple[bool, str]:
    """Whether the menu bar app can run here. Returns (ok, reason-if-not)."""
    if platform.system() != "Darwin":
        return False, "the menu bar app is macOS-only"
    if importlib.util.find_spec("rumps") is None:
        return False, "the menu bar app needs the 'menubar' extra (rumps)"
    return True, ""


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid() -> int | None:
    """The recorded menu-app PID if its process is still alive, else None."""
    if not MENU_PIDFILE.exists():
        return None
    try:
        pid = int(MENU_PIDFILE.read_text().strip())
    except ValueError:
        return None
    return pid if _alive(pid) else None


def start_background(config: Config) -> tuple[bool, str]:
    """Spawn the menu bar app detached. Idempotent. Returns (ok, msg)."""
    ok, why = available()
    if not ok:
        return False, why
    if read_pid() is not None:
        return True, "menu bar app already running"

    HEARCODE_HOME.mkdir(parents=True, exist_ok=True)
    # The detached child runs the real (foreground) GUI run loop — `--foreground`
    # stops it from recursing back into another background spawn.
    cmd = [
        sys.executable, "-m", "hearcode",
        "--port", str(config.port), "menu", "--foreground",
    ]
    with MENU_LOGFILE.open("a") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    MENU_PIDFILE.write_text(str(proc.pid))
    # No /health to poll (it's a GUI); just make sure it didn't die on launch
    # (bad import, no window server) before reporting success.
    time.sleep(0.6)
    if proc.poll() is not None:
        MENU_PIDFILE.unlink(missing_ok=True)
        return False, f"menu bar app exited immediately — see {MENU_LOGFILE}"
    return True, f"menu bar app started (pid {proc.pid})"


def stop() -> tuple[bool, str]:
    """SIGTERM the recorded menu bar app. Returns (ok, msg)."""
    pid = read_pid()
    if pid is None:
        MENU_PIDFILE.unlink(missing_ok=True)
        return False, "no running menu bar app"
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        MENU_PIDFILE.unlink(missing_ok=True)
        return False, f"could not stop menu bar app (pid {pid}): {exc}"
    MENU_PIDFILE.unlink(missing_ok=True)
    return True, f"stopped menu bar app (pid {pid})"
