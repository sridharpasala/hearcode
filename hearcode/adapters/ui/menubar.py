"""Layer 3 — the macOS menu bar app (a driving adapter over the daemon).

A tiny `rumps` status-bar item that lets you Start/Stop the daemon, switch the
soundtrack theme live, and see the agent's current mood — without touching a
terminal. It is a *client*: mood/theme come from the daemon's `/state` and
`/theme` HTTP surface, and Start/Stop reuse the same `daemon` lifecycle helpers
the CLI uses. No domain logic lives here.

`rumps` is an optional dependency (the `menubar` extra); importing this module
without it raises ImportError, which the CLI turns into an install hint.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import rumps

from ...infrastructure import daemon
from ...infrastructure.config import Config

# Mood → a glyph shown as the menu bar title, so you can read the agent's state
# at a glance from the top of the screen.
_INTENT_ICON = {
    "explore": "🔍",
    "build": "🔨",
    "action": "⚡",
    "tension": "🌀",
    "error": "🔴",
    "stuck": "🌀",
    "needs_input": "🔔",
    "done": "✅",
    "idle": "🎵",
}
_STOPPED_ICON = "♪"

_REFRESH_SECONDS = 1.0

# Friendly labels for the pad ambience styles (keys come from the daemon's
# /state `pad_styles`; anything unknown falls back to a title-cased key).
_PAD_LABELS = {
    "low_warm": "Low & warm",
    "open_fifths": "Open fifths",
    "detuned_soft": "Detuned soft",
    "airy": "Airy minimal",
    "classic": "Present",
}

# A short, curated set of good English `say` voices offered in the menu (the Mac
# ships ~180, mostly novelty/multilingual — too many for a menu). None == the
# system default. The list is filtered to what's actually installed at startup.
_CURATED_VOICES: list[tuple[str, str | None]] = [
    ("System default", None),
    ("Samantha (US)", "Samantha"),
    ("Daniel (UK)", "Daniel"),
    ("Karen (AU)", "Karen"),
    ("Moira (IE)", "Moira"),
    ("Tessa (ZA)", "Tessa"),
    ("Rishi (IN)", "Rishi"),
    ("Fred (retro)", "Fred"),
    ("Zarvox (robot)", "Zarvox"),
]


def _get_state(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=0.5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        return None


def _post(port: int, path: str, body: dict) -> dict | None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        return None


def _installed_voice_names() -> set[str]:
    """Names of the macOS voices installed (first token of each `say -v ?` row)."""
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=3)
    except Exception:
        return set()
    names = set()
    for line in out.stdout.splitlines():
        # "Name   lang   # comment" — split on 2+ spaces; the name may contain one.
        parts = re.split(r"\s{2,}", line.strip())
        if parts and parts[0]:
            names.add(parts[0])
    return names


def _preview_voice(voice: str | None) -> None:
    """Speak a short sample in the chosen voice so you can hear it immediately."""
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    cmd.append("This is how HearCode will call you.")
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class HearCodeApp(rumps.App):
    def __init__(self, config: Config) -> None:
        super().__init__("HearCode", title=_STOPPED_ICON, quit_button="Quit HearCode")
        self._config = config
        self._port = config.port

        self._status = rumps.MenuItem("starting…")
        self._start = rumps.MenuItem("Start daemon", callback=self._on_start)
        self._stop = rumps.MenuItem("Stop daemon", callback=self._on_stop)

        # The demo is a subprocess that scripts events at the daemon. The one menu
        # item toggles Play/Stop so a long demo can be cut short.
        self._demo = rumps.MenuItem("Play demo", callback=self._on_simulate)
        self._demo_proc: subprocess.Popen | None = None

        # Theme submenu — one checkable item per available theme. The list is
        # discovered from /state; until the daemon answers, seed it from config.
        self._theme_menu = rumps.MenuItem("Theme")
        self._theme_items: dict[str, rumps.MenuItem] = {}
        self._ensure_theme_items([config.theme])

        # Ambience submenu — the selectable pad textures. Discovered from /state;
        # until the daemon answers, seed it from the configured style.
        self._pad_menu = rumps.MenuItem("Ambience")
        self._pad_items: dict[str, rumps.MenuItem] = {}
        self._ensure_pad_items([getattr(config, "pad_style", "low_warm")])

        # Voice submenu — the curated voices that are actually installed. Each
        # item both switches the daemon's alert voice and previews it aloud.
        self._voice_menu = rumps.MenuItem("Alert voice")
        self._voice_items: dict[str | None, rumps.MenuItem] = {}
        installed = _installed_voice_names()
        for label, value in _CURATED_VOICES:
            if value is not None and value not in installed:
                continue  # not on this Mac — skip so the menu has no dead entries
            item = rumps.MenuItem(label, callback=self._on_voice)
            item._hearcode_voice = value
            self._voice_items[value] = item
            self._voice_menu[label] = item

        self.menu = [
            self._status,
            None,
            self._start,
            self._stop,
            None,
            self._theme_menu,
            self._pad_menu,
            self._voice_menu,
            None,
            self._demo,
            rumps.MenuItem("Run doctor", callback=self._on_doctor),
        ]

        rumps.Timer(self._refresh, _REFRESH_SECONDS).start()
        self._refresh(None)

    # ---- menu actions (long work is threaded so the UI never freezes) ------

    # Long-running lifecycle calls run off the main thread so the menu never
    # freezes; the periodic Timer (which runs *on* the main thread) is what
    # repaints the UI, so worker threads must not touch AppKit objects directly.
    # These click handlers *do* run on the main thread, so they flip the
    # Start/Stop enablement optimistically for instant feedback; the next
    # refresh tick reconciles it with reality.
    def _on_start(self, _sender) -> None:  # noqa: ANN001
        self._status.title = "starting daemon…"
        self._start.set_callback(None)          # grey out Start
        self._stop.set_callback(self._on_stop)  # enable Stop
        threading.Thread(target=daemon.start_background, args=(self._config,), daemon=True).start()

    def _on_stop(self, _sender) -> None:  # noqa: ANN001
        self._status.title = "stopping daemon…"
        self._stop.set_callback(None)             # grey out Stop
        self._start.set_callback(self._on_start)  # enable Start
        self.title = _STOPPED_ICON                # mute the mood glyph at once
        threading.Thread(target=daemon.stop, args=(self._port,), daemon=True).start()

    def _on_theme(self, sender) -> None:  # noqa: ANN001
        theme = getattr(sender, "_hearcode_theme", None)
        if not theme:
            return
        if _post(self._port, "/theme", {"theme": theme}) is None:
            rumps.notification("HearCode", "Theme", "start the daemon first")
        self._refresh(None)

    def _on_pad(self, sender) -> None:  # noqa: ANN001
        style = getattr(sender, "_hearcode_pad", None)
        if not style:
            return
        if _post(self._port, "/pad", {"style": style}) is None:
            rumps.notification("HearCode", "Ambience", "start the daemon first")
        self._refresh(None)

    def _on_voice(self, sender) -> None:  # noqa: ANN001
        voice = getattr(sender, "_hearcode_voice", None)
        if _post(self._port, "/voice", {"voice": voice}) is None:
            rumps.notification("HearCode", "Alert voice", "start the daemon first")
            return
        _preview_voice(voice)  # speak a sample so the choice is audible
        self._refresh(None)

    def _on_simulate(self, _sender) -> None:  # noqa: ANN001
        # One item, two states: start the scripted demo, or stop it mid-run.
        if self._demo_proc is not None and self._demo_proc.poll() is None:
            self._stop_demo()
            return
        if not (daemon.is_healthy(self._port)):
            rumps.notification("HearCode", "Play demo", "start the daemon first")
            return
        self._demo_proc = subprocess.Popen(
            [sys.executable, "-m", "hearcode", "--port", str(self._port), "simulate"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._demo.title = "Stop demo"

    def _stop_demo(self) -> None:
        """Cut a running demo short and let the soundtrack resolve to rest."""
        proc = self._demo_proc
        if proc is not None and proc.poll() is None:
            proc.terminate()  # simulate installs no handler — SIGTERM ends it at once
        self._demo_proc = None
        self._demo.title = "Play demo"
        # The demo left the daemon in whatever mood it reached; send a Stop event
        # so the music resolves and decays instead of hanging on that state.
        _post(self._port, "/event", {"hook_event_name": "Stop"})

    def _on_doctor(self, _sender) -> None:  # noqa: ANN001
        out = subprocess.run(
            [sys.executable, "-m", "hearcode", "--port", str(self._port), "doctor"],
            capture_output=True,
            text=True,
        )
        rumps.alert("HearCode doctor", out.stdout or out.stderr or "(no output)")

    # ---- periodic refresh --------------------------------------------------

    def _refresh(self, _timer) -> None:  # noqa: ANN001
        # If the demo finished on its own, flip the toggle back to "Play demo".
        if self._demo_proc is not None and self._demo_proc.poll() is not None:
            self._demo_proc = None
            self._demo.title = "Play demo"

        snap = _get_state(self._port)
        # Liveness is the /health check, not /state — so a daemon that's up but
        # too old to serve /state still counts as running (and can be stopped),
        # rather than looking dead and leaving Start/Stop both wrong.
        up = snap is not None or daemon.is_healthy(self._port)
        # Enable exactly the action that applies (a None callback greys it out).
        self._start.set_callback(None if up else self._on_start)
        self._stop.set_callback(self._on_stop if up else None)

        if snap is None:
            self.title = _STOPPED_ICON
            self._status.title = (
                "daemon: running — restart to enable theme/mood"
                if up else "daemon: stopped"
            )
            return

        intent = snap.get("intent", "idle")
        intensity = float(snap.get("intensity", 0.0))
        health = float(snap.get("health", 0.5))
        self.title = _INTENT_ICON.get(intent, _STOPPED_ICON)
        dot = "🟢" if health >= 0.7 else "🔴" if health <= 0.3 else "⚪️"
        self._status.title = f"{intent} · intensity {intensity:.1f} · build {dot}"

        self._ensure_theme_items(snap.get("themes", []))
        current = snap.get("theme")
        for name, item in self._theme_items.items():
            item.state = 1 if name == current else 0

        self._ensure_pad_items(snap.get("pad_styles", []))
        current_pad = snap.get("pad_style")
        for name, item in self._pad_items.items():
            item.state = 1 if name == current_pad else 0

        current_voice = snap.get("voice")  # None == system default
        for value, item in self._voice_items.items():
            item.state = 1 if value == current_voice else 0

    def _ensure_theme_items(self, themes: list[str]) -> None:
        for name in themes:
            if name in self._theme_items:
                continue
            item = rumps.MenuItem(name.capitalize(), callback=self._on_theme)
            item._hearcode_theme = name
            self._theme_items[name] = item
            self._theme_menu[name] = item

    def _ensure_pad_items(self, styles: list[str]) -> None:
        for name in styles:
            if name in self._pad_items:
                continue
            label = _PAD_LABELS.get(name, name.replace("_", " ").capitalize())
            item = rumps.MenuItem(label, callback=self._on_pad)
            item._hearcode_pad = name
            self._pad_items[name] = item
            self._pad_menu[name] = item


def _hide_dock_icon() -> None:
    """Run as a menu bar *accessory* — a status item only, no Dock icon.

    Launched as a plain script the process is a regular app (the Python rocket
    shows in the Dock). Switching the activation policy to Accessory before the
    run loop starts makes it a background/agent app: menu bar only, no Dock icon
    and no app-switcher entry.
    """
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass  # non-Mac / PyObjC missing — the caller already guards for that


def run(config: Config) -> None:
    """Launch the menu bar app (blocks on the macOS run loop until quit)."""
    _hide_dock_icon()
    HearCodeApp(config).run()
