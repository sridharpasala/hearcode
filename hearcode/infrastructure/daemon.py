"""Layer 4 — background daemon lifecycle (detached spawn + stop via a pidfile).

So you don't have to babysit a terminal: `start --background` / `init` spawn the
daemon in its own session with its stdout teed to a log, recording the child PID
in `~/.hearcode/daemon.pid`; `stop` reads that PID and sends SIGTERM for a clean
shutdown. Health is confirmed over the existing HTTP `/health` endpoint, so a
stale pidfile (process gone) never reports a false "running".
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .config import HEARCODE_HOME, DEFAULT_PORT, Config

PIDFILE = HEARCODE_HOME / "daemon.pid"
LOGFILE = HEARCODE_HOME / "daemon.log"


def is_healthy(port: int, timeout: float = 1.0) -> bool:
    """True if a daemon answers /health on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout):
            return True
    except OSError:
        # URLError subclasses OSError; a reset mid-shutdown is a raw OSError too.
        return False


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid() -> int | None:
    """The recorded daemon PID if its process is still alive, else None."""
    if not PIDFILE.exists():
        return None
    try:
        pid = int(PIDFILE.read_text().strip())
    except ValueError:
        return None
    return pid if _alive(pid) else None


def start_background(config: Config, wait_seconds: float = 12.0) -> tuple[bool, str]:
    """Spawn the daemon detached; wait until it answers /health. Returns (ok, msg)."""
    # Idempotent: a daemon already answering on this port is the desired end state.
    if is_healthy(config.port):
        return True, f"daemon already running on port {config.port}"

    HEARCODE_HOME.mkdir(parents=True, exist_ok=True)
    # The detached child runs the real (foreground) server — `--foreground` stops
    # it from recursing back into another background spawn.
    cmd = [
        sys.executable, "-u", "-m", "hearcode",
        "--port", str(config.port), "start", "--foreground",
    ]
    if config.silent:
        cmd.append("--silent")
    # Detached session + inherited env (carries HEARCODE_THEME / HEARCODE_ASSETS),
    # output teed to the log so a crash is diagnosable.
    with LOGFILE.open("a") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    PIDFILE.write_text(str(proc.pid))

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if is_healthy(config.port):
            return True, f"daemon started (pid {proc.pid}) on port {config.port}"
        if proc.poll() is not None:
            return False, f"daemon exited early — see {LOGFILE}"
        time.sleep(0.3)
    return False, f"daemon did not become healthy in {wait_seconds:.0f}s — see {LOGFILE}"


def _request_shutdown(port: int) -> bool:
    """Ask a running daemon to stop itself via POST /shutdown. True if accepted."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/shutdown",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False  # no such endpoint (an old daemon) or an error
    except OSError:
        return True  # connection dropped as the daemon exited — that's success


def stop(port: int = DEFAULT_PORT, timeout: float = 5.0) -> tuple[bool, str]:
    """Stop the daemon and wait for it to exit. Returns (ok, msg).

    Primary path is a SIGTERM to the recorded PID; if the pidfile is missing or
    stale but a daemon is still answering on `port` (e.g. it was already healthy
    when last started, so no PID was recorded), fall back to asking it to shut
    itself down over HTTP so the caller isn't left unable to stop it.
    """
    pid = read_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            PIDFILE.unlink(missing_ok=True)
            return False, f"could not stop pid {pid}: {exc}"
        deadline = time.time() + timeout
        while time.time() < deadline and _alive(pid):
            time.sleep(0.1)
        PIDFILE.unlink(missing_ok=True)
        if not _alive(pid):
            return True, f"stopped daemon (pid {pid})"
        return False, f"daemon (pid {pid}) did not exit within {timeout:.0f}s"

    # No usable pidfile — but is one actually running on the port?
    if not is_healthy(port, timeout=1.0):
        PIDFILE.unlink(missing_ok=True)
        return False, "no running daemon found"
    if not _request_shutdown(port):
        return False, f"daemon on port {port} did not accept shutdown"
    deadline = time.time() + timeout
    while time.time() < deadline and is_healthy(port, timeout=0.5):
        time.sleep(0.1)
    PIDFILE.unlink(missing_ok=True)
    if is_healthy(port, timeout=0.5):
        return False, f"daemon on port {port} did not stop within {timeout:.0f}s"
    return True, f"stopped daemon on port {port}"
