"""Layer 4 — command-line entry point.

    hearcode init                  one-step setup: stems + hooks + daemon + menu bar app
    hearcode start                 start the daemon in the background (-f to attach)
    hearcode stop                  stop the background daemon
    hearcode theme [name]          show or switch the soundtrack theme, live
    hearcode voice [name]          show/switch the spoken-alert voice (--list for all)
    hearcode menu                  launch the macOS menu bar app in the background
    hearcode doctor                check the install (python, audio, stems, hooks, daemon)
    hearcode install               wire hooks into ~/.claude/settings.json
    hearcode uninstall             remove HearCode hooks (--purge deletes everything)
    hearcode simulate              demo: fire a scripted agent session at the daemon
    hearcode status                check whether the daemon is up
    hearcode recap                 print + render a recap of the last session
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .infrastructure import installer
from .infrastructure.config import Config
from .infrastructure.server import serve


def _post(port: int, path: str, payload: dict) -> dict | None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        return None


def _get(port: int, path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1.0) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        return None


def _post_event(port: int, payload: dict) -> dict | None:
    return _post(port, "/event", payload)


# A scripted "agent session" for the demo, broken into narrated phases. Each
# step is (hook_event_name, tool_name, tool_input, is_error, hold_seconds):
#   tool_input  realistic dict the daemon mines for a "target" fingerprint
#               (file_path / command / pattern / …) — drives stuck-loop detection.
#   is_error    True marks a failed tool (fires the error sting / builds anxiety).
#   hold        seconds to wait after firing, so the motif/mood is audible.
#
# A "Step" is just a tuple; spelled out here for readability of the tables below.
def _step(hook, tool, tool_input=None, error=False, hold=1.0):
    return (hook, tool, tool_input or {}, error, hold)


# --- Phase 1: Explore — varied read-only tools, each with its own motif, calm.
_EXPLORE = [
    _step("PreToolUse", "Read", {"file_path": "hearcode/cli.py"}, hold=1.1),
    _step("PreToolUse", "Grep", {"pattern": "def main", "path": "hearcode"}, hold=1.1),
    _step("PreToolUse", "Glob", {"pattern": "hearcode/**/*.py"}, hold=1.1),
    _step("PreToolUse", "Read", {"file_path": "hearcode/domain/session.py"}, hold=1.1),
    _step("PreToolUse", "WebSearch", {"query": "python urllib post json"}, hold=1.1),
    _step("PreToolUse", "Task", {"description": "map the audio pipeline"}, hold=1.2),
]

# --- Phase 2: Build — write/edit several files; intensity ramps up.
_BUILD = [
    _step("PreToolUse", "Write", {"file_path": "hearcode/mixer.py"}, hold=0.8),
    _step("PreToolUse", "Edit", {"file_path": "hearcode/mixer.py"}, hold=0.8),
    _step("PreToolUse", "Edit", {"file_path": "hearcode/server.py"}, hold=0.8),
    _step("PreToolUse", "Write", {"file_path": "tests/test_mixer.py"}, hold=0.8),
    _step("PreToolUse", "Bash", {"command": "ruff check hearcode"}, hold=0.8),
    _step("PreToolUse", "Edit", {"file_path": "hearcode/server.py"}, hold=0.8),
    # Tests pass -> build health turns green, harmony brightens toward major.
    _step("PostToolUse", "Bash", {"command": "pytest -q"}, hold=1.2),
]

# --- Phase 3: Productive iteration — edit the SAME file repeatedly, NO errors.
# Repetition alone must stay calm (anxiety ~0): this proves no false positive.
_ITERATE = [
    _step("PreToolUse", "Edit", {"file_path": "hearcode/mixer.py"}, hold=0.9),
    _step("PreToolUse", "Edit", {"file_path": "hearcode/mixer.py"}, hold=0.9),
    _step("PreToolUse", "Edit", {"file_path": "hearcode/mixer.py"}, hold=0.9),
    _step("PreToolUse", "Edit", {"file_path": "hearcode/mixer.py"}, hold=0.9),
]


# --- Phase 4: Doom loop — hammer the SAME target with failures; anxiety climbs.
def _doomloop_steps(rounds: int = 4):
    steps = []
    for _ in range(rounds):
        steps.append(_step("PreToolUse", "Edit", {"file_path": "auth.py"}, hold=0.7))
        steps.append(_step("PreToolUse", "Bash", {"command": "pytest"}, hold=0.7))
        steps.append(
            _step(
                "PostToolUseFailure",
                "Bash",
                {"command": "pytest"},
                error=True,
                hold=1.2,
            )
        )
    return steps


_DOOMLOOP = _doomloop_steps()

# --- Phase 5: Needs you — agent blocks for permission / attention.
# Fires the unmissable alert chime + a spoken announcement (macOS `say`).
_NEEDS_YOU = [
    _step("PermissionRequest", "Bash", {"command": "git push --force"}, hold=2.0),
    _step("Notification", None, {}, hold=2.0),
]

# --- Phase 6: Recovery & done — a clean Bash, then Stop resolves the tension.
_RECOVERY = [
    _step("PreToolUse", "Edit", {"file_path": "auth.py"}, hold=0.8),
    _step("PreToolUse", "Bash", {"command": "pytest"}, hold=0.8),
    _step("PostToolUse", "Bash", {"command": "pytest"}, hold=1.2),
    _step("Stop", None, {}, hold=0.0),
]

# Ordered phases: key -> (header, note, steps). `full` runs them all in order.
_PHASES = [
    ("explore", "1. EXPLORE", "varied read-only tools — listen for distinct motifs", _EXPLORE),
    ("build", "2. BUILD", "writing & editing files — intensity ramps up", _BUILD),
    (
        "iterate",
        "3. PRODUCTIVE ITERATION",
        "same file edited repeatedly, no errors — anxiety should stay ~0",
        _ITERATE,
    ),
    (
        "doomloop",
        "4. DOOM LOOP",
        "same target keeps failing — anxiety climbs past 0.6, stuck alert fires",
        _DOOMLOOP,
    ),
    (
        "needsyou",
        "5. NEEDS YOU",
        "agent blocks for permission/attention — alert chime + spoken announcement",
        _NEEDS_YOU,
    ),
    (
        "recovery",
        "6. RECOVERY & DONE",
        "a clean run, then Stop — anxiety resolves back to 0",
        _RECOVERY,
    ),
]
_SCENARIOS = ["full"] + [key for key, _h, _n, _s in _PHASES]


def _fire_step(port: int, step: tuple) -> dict | None:
    hook, tool, tool_input, error, hold = step
    payload: dict = {"hook_event_name": hook, "tool_name": tool}
    if tool_input:
        payload["tool_input"] = tool_input
    if error:
        payload["tool_error"] = "exit status 1"
    result = _post_event(port, payload)

    label = f"{hook}({tool})" if tool else hook
    target = next(iter(tool_input.values()), "") if tool_input else ""
    detail = f"{target}" + ("  [error]" if error else "")
    if result is None:
        line = f"{result}"
    else:
        health = result.get("health", 0.5)
        build = " 🟢" if health >= 0.7 else (" 🔴" if health <= 0.3 else "")
        flag = " ⚠ STUCK" if result.get("anxiety", 0) >= 0.6 else ""
        line = (
            f"intent={result['intent']:<7} "
            f"intensity={result['intensity']:.2f} "
            f"anxiety={result['anxiety']:.2f} "
            f"health={health:.2f}{build}{flag}"
        )
    print(f"  → {label:<24} {detail:<22} {line}")
    time.sleep(hold)
    return result


def _run_phase(port: int, header: str, note: str, steps: list) -> None:
    print(f"\n=== {header} — {note} ===")
    for step in steps:
        _fire_step(port, step)


def _cmd_simulate(args: argparse.Namespace) -> int:
    if _post_event(args.port, {"hook_event_name": "SessionStart"}) is None:
        print("daemon not reachable — run `hearcode start` in another terminal first")
        return 1

    scenario = getattr(args, "scenario", "full")
    phases = _PHASES if scenario == "full" else [
        p for p in _PHASES if p[0] == scenario
    ]
    if not phases:
        print(f"unknown scenario {scenario!r}; choose one of: {', '.join(_SCENARIOS)}")
        return 1

    # Resolve any tension left over in the long-lived daemon from a previous run
    # so each scenario starts from a clean, reproducible slate (anxiety 0).
    _post_event(args.port, {"hook_event_name": "Stop"})

    print(f"simulating an agent session (scenario: {scenario}) — listen!")
    for key, header, note, steps in phases:
        _run_phase(args.port, header, note, steps)
    print("\ndone.")
    return 0


def _bar(value: float, width: int = 12) -> str:
    filled = int(round(max(0.0, min(1.0, value)) * width))
    return "█" * filled + "·" * (width - filled)


def _cmd_recap(args: argparse.Namespace) -> int:
    from .adapters.recap.recap_renderer import (
        RecapRenderer,
        latest_session,
        load_session,
        session_stats,
    )

    config = Config.load()
    path = Path(args.session) if args.session else latest_session(config.sessions_dir)
    if path is None or not Path(path).exists():
        print(f"no session log found in {config.sessions_dir} — run a session first")
        return 1

    entries = load_session(Path(path))
    if not entries:
        print(f"session {path} is empty")
        return 1

    stats = session_stats(entries)
    health_word = (
        "green ✅" if stats.final_health >= 0.7
        else "red ❌" if stats.final_health <= 0.3
        else "neutral"
    )
    print(f"\n♪ HearCode session recap — {Path(path).name}")
    print(f"  {stats.moments} moments over {stats.duration_seconds:.0f}s of work\n")
    print("  time spent in each mood:")
    for intent, count in stats.intents.most_common():
        frac = count / stats.moments
        print(f"    {intent:<11} {_bar(frac)} {count:>3}")
    if stats.tools:
        top = ", ".join(f"{t}×{n}" for t, n in stats.tools.most_common(5))
        print(f"\n  busiest tools: {top}")
    for cue, label in (("error", "errors"), ("stuck", "stuck alerts"),
                       ("needs_input", "needs-you alerts")):
        if stats.cues.get(cue):
            print(f"  {label}: {stats.cues[cue]}")
    print(
        f"\n  peak intensity {stats.peak_intensity:.2f} · "
        f"peak anxiety {stats.peak_anxiety:.2f} · "
        f"ended {health_word}"
    )

    want_audio = not args.no_audio
    want_image = not args.no_image
    if not (want_audio or want_image):
        return 0
    try:
        from .adapters.mixer.stem_pack import ensure_assets

        stems_dir = ensure_assets(config.assets_dir, config.theme, print)
        renderer = RecapRenderer(assets_dir=stems_dir)
        mix, sched = renderer.mix_for(entries, seconds=args.seconds)
        out_wav = Path(args.out) if args.out else Path(path).with_suffix(".recap.wav")
        if want_audio:
            renderer.write_wav(out_wav, mix)
            print(f"\n  rendered {args.seconds:.0f}s recap → {out_wav}")
            if args.play and sys.platform == "darwin":
                import subprocess

                subprocess.Popen(["afplay", str(out_wav)])
                print("  playing…")
        if want_image:
            from .adapters.recap.waveform_export import WaveformExporter

            out_svg = out_wav.with_suffix(".svg")
            WaveformExporter().export(
                mix, renderer.samplerate, sched, out_svg,
                seconds=args.seconds, title=Path(path).stem, stats=stats,
            )
            print(f"  exported waveform → {out_svg}")
    except Exception as exc:
        print(f"\n  (render skipped: {exc})")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{args.port}/health", timeout=1.0
        ) as resp:
            print(f"daemon up on port {args.port}: {resp.read().decode()}")
            return 0
    except urllib.error.URLError:
        print(f"daemon not running on port {args.port}")
        return 1


def _cmd_start(args: argparse.Namespace) -> int:
    config = dataclasses.replace(
        Config.load(), port=args.port, silent=args.silent or Config.load().silent
    )
    if getattr(args, "foreground", False):
        serve(config)
        return 0
    from .infrastructure import daemon

    ok, msg = daemon.start_background(config)
    print(msg)
    return 0 if ok else 1


def _cmd_init(args: argparse.Namespace) -> int:
    from .adapters.mixer.stem_pack import ensure_assets
    from .infrastructure import daemon

    config = dataclasses.replace(Config.load(), port=args.port)
    print("setting up HearCode:")
    ensure_assets(config.assets_dir, config.theme, lambda m: print(f"  {m}"))
    print(f"  ✓ stem pack '{config.theme}' ready in {config.assets_dir}")

    path = installer.install(config.port)
    print(f"  ✓ Claude Code hooks installed in {path}")

    ok, msg = daemon.start_background(config)
    print(f"  {'✓' if ok else '✗'} {msg}")
    if not ok:
        return 1

    # Bring up the menu bar app automatically (macOS + the `menubar` extra).
    # Optional UI, so a missing dependency is a soft skip — init still succeeds.
    if not getattr(args, "no_menu", False):
        from .infrastructure import menu_app

        m_ok, m_msg = menu_app.start_background(config)
        if m_ok:
            print(f"  ✓ {m_msg}")
        elif "rumps" in m_msg:
            print("  · menu bar app skipped — enable it with:")
            print("      uv tool install 'hearcode[menubar]'")
        else:
            print(f"  · menu bar app skipped ({m_msg})")

    print("\nHearCode is live — use Claude Code normally and you'll hear it.")
    print("  hear a demo:  hearcode simulate")
    print("  check setup:  hearcode doctor")
    print("  stop it:      hearcode stop")
    return 0


def _cmd_theme(args: argparse.Namespace) -> int:
    name = getattr(args, "name", None)
    if not name:
        snap = _get(args.port, "/state")
        if snap is None:
            print(f"daemon not running on port {args.port} — run `hearcode start` first")
            return 1
        available = ", ".join(snap.get("themes", []))
        print(f"current theme: {snap.get('theme')}")
        print(f"available:     {available}")
        print("switch with:   hearcode theme <name>")
        return 0

    result = _post(args.port, "/theme", {"theme": name})
    if result is None:
        print(f"daemon not running on port {args.port} — run `hearcode start` first")
        return 1
    print(result.get("message", ""))
    return 0 if result.get("ok") else 1


def _cmd_pad(args: argparse.Namespace) -> int:
    name = getattr(args, "name", None)
    if not name:
        snap = _get(args.port, "/state")
        if snap is None:
            print(f"daemon not running on port {args.port} — run `hearcode start` first")
            return 1
        available = ", ".join(snap.get("pad_styles", []))
        print(f"current ambience: {snap.get('pad_style')}")
        print(f"available:        {available}")
        print("switch with:      hearcode pad <name>")
        return 0

    result = _post(args.port, "/pad", {"style": name})
    if result is None:
        print(f"daemon not running on port {args.port} — run `hearcode start` first")
        return 1
    print(result.get("message", ""))
    return 0 if result.get("ok") else 1


def _list_say_voices() -> None:
    """Print the macOS `say` voices installed on this machine."""
    import subprocess

    try:
        out = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=3
        )
    except Exception as exc:
        print(f"could not list voices ({exc}) — `say` is macOS-only")
        return
    print("installed macOS voices (use the name, e.g. `hearcode voice Daniel`):\n")
    print(out.stdout.rstrip())


def _cmd_voice(args: argparse.Namespace) -> int:
    if getattr(args, "list", False):
        _list_say_voices()
        return 0

    name = getattr(args, "name", None)
    if name is None:
        snap = _get(args.port, "/state")
        if snap is None:
            print(f"daemon not running on port {args.port} — run `hearcode start` first")
            return 1
        print(f"current voice: {snap.get('voice') or 'system default'}")
        print("list all voices: hearcode voice --list")
        print("switch:          hearcode voice <Name>   (e.g. hearcode voice Daniel)")
        print("system default:  hearcode voice default")
        return 0

    voice = None if name.lower() in ("default", "system", "none") else name
    result = _post(args.port, "/voice", {"voice": voice})
    if result is None:
        print(f"daemon not running on port {args.port} — run `hearcode start` first")
        return 1
    print(result.get("message", ""))
    return 0 if result.get("ok") else 1


def _cmd_menu(args: argparse.Namespace) -> int:
    from .infrastructure import menu_app

    if getattr(args, "stop", False):
        ok, msg = menu_app.stop()
        print(msg)
        return 0 if ok else 1

    config = dataclasses.replace(Config.load(), port=args.port)
    # --foreground is the internal mode the detached spawner uses to actually run
    # the GUI run loop; users just run `hearcode menu` and it backgrounds itself.
    if getattr(args, "foreground", False):
        try:
            from .adapters.ui.menubar import run
        except ImportError:
            print("the menu bar app needs `rumps`:")
            print("  uv tool install 'hearcode[menubar]'   # or: pip install rumps")
            return 1
        run(config)
        return 0

    ok, msg = menu_app.start_background(config)
    print(msg)
    return 0 if ok else 1


def _cmd_stop(args: argparse.Namespace) -> int:
    from .infrastructure import daemon

    ok, msg = daemon.stop(args.port)
    print(msg)
    return 0 if ok else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .infrastructure import daemon

    config = dataclasses.replace(Config.load(), port=args.port)
    checks: list[tuple[bool, str]] = []

    py = sys.version_info
    checks.append((py[:2] >= (3, 13), f"Python {py.major}.{py.minor} (needs ≥ 3.13)"))

    try:
        import sounddevice as sd

        out = sd.query_devices(kind="output")
        checks.append((True, f"audio output device: {out['name']}"))
    except Exception as exc:
        checks.append((False, f"audio output unavailable ({exc})"))

    stems = config.stems_dir
    n = len(list(stems.glob("*.wav"))) if stems.is_dir() else 0
    checks.append((
        n > 0,
        f"stem pack '{config.theme}': {n} stems in {stems}"
        + ("" if n else " — run `hearcode init`"),
    ))

    sp = installer.settings_path()
    hooked = sp.exists() and f"127.0.0.1:{config.port}/event" in sp.read_text()
    checks.append((
        hooked,
        f"Claude Code hooks in {sp}" + ("" if hooked else " — run `hearcode init`"),
    ))

    up = daemon.is_healthy(config.port)
    pid = daemon.read_pid()
    checks.append((
        up,
        f"daemon on port {config.port}"
        + (f" (pid {pid})" if up and pid else "")
        + ("" if up else " — run `hearcode start --background`"),
    ))

    print("hearcode doctor:")
    for ok, label in checks:
        print(f"  {'✓' if ok else '✗'} {label}")
    all_ok = all(ok for ok, _ in checks)
    print("\n" + ("all good — HearCode is ready." if all_ok else "some checks failed (see above)."))
    return 0 if all_ok else 1


def _cmd_install(args: argparse.Namespace) -> int:
    path = installer.install(args.port)
    print(f"installed HearCode hooks into {path}")
    print("start the daemon with `hearcode start`, then run Claude Code normally.")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    path = installer.uninstall(args.port)
    print(f"removed HearCode hooks from {path}")
    if not getattr(args, "purge", False):
        print("(daemon, menu, and ~/.hearcode data left in place — use --purge to remove them too)")
        return 0

    # Full removal: stop the running services and delete all generated data.
    import shutil

    from .infrastructure import daemon, menu_app
    from .infrastructure.config import HEARCODE_HOME

    _, menu_msg = menu_app.stop()
    print(f"  {menu_msg}")
    _, daemon_msg = daemon.stop(args.port)
    print(f"  {daemon_msg}")
    if HEARCODE_HOME.exists():
        shutil.rmtree(HEARCODE_HOME, ignore_errors=True)
        print(f"  removed data dir {HEARCODE_HOME}")

    # A running process can't reliably remove the CLI that launched it, so point
    # the user at the one manual step left to fully delete the app.
    print("\nHearCode is uninstalled. To remove the command itself, run whichever installed it:")
    print("  uv tool uninstall hearcode   # or: pipx uninstall hearcode   # or: pip uninstall hearcode")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hearcode", description=__doc__)
    parser.add_argument("--port", type=int, default=Config.load().port)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init", help="one-step setup: stems + hooks + daemon + menu bar app"
    )
    p_init.add_argument(
        "--no-menu", action="store_true",
        help="don't auto-launch the macOS menu bar app",
    )
    p_init.set_defaults(func=_cmd_init)

    p_start = sub.add_parser("start", help="start the daemon in the background")
    p_start.add_argument("--silent", action="store_true", help="no audio; log decisions")
    p_start.add_argument(
        "--foreground", "-f", action="store_true",
        help="run attached (Ctrl-C to quit) instead of backgrounding",
    )
    p_start.set_defaults(func=_cmd_start)

    sub.add_parser("stop", help="stop the background daemon").set_defaults(
        func=_cmd_stop
    )

    p_theme = sub.add_parser("theme", help="show or switch the soundtrack theme, live")
    p_theme.add_argument(
        "name", nargs="?", help="theme to switch to (omit to show current + available)"
    )
    p_theme.set_defaults(func=_cmd_theme)

    p_pad = sub.add_parser("pad", help="show or switch the ambient pad style, live")
    p_pad.add_argument(
        "name", nargs="?", help="ambience to switch to (omit to show current + available)"
    )
    p_pad.set_defaults(func=_cmd_pad)

    p_voice = sub.add_parser("voice", help="show/switch the spoken-alert voice, live")
    p_voice.add_argument(
        "name", nargs="?", help="voice to switch to (omit to show current; 'default' resets)"
    )
    p_voice.add_argument(
        "--list", action="store_true", help="list every macOS voice installed"
    )
    p_voice.set_defaults(func=_cmd_voice)

    p_menu = sub.add_parser(
        "menu", help="launch the macOS menu bar app in the background"
    )
    p_menu.add_argument(
        "--stop", action="store_true", help="stop the background menu bar app"
    )
    # Internal: run the GUI run loop attached (the detached spawner uses this).
    p_menu.add_argument("--foreground", "-f", action="store_true", help=argparse.SUPPRESS)
    p_menu.set_defaults(func=_cmd_menu)
    sub.add_parser(
        "doctor", help="check python, audio, stems, hooks, and the daemon"
    ).set_defaults(func=_cmd_doctor)

    sub.add_parser("install", help="add hooks to settings.json").set_defaults(
        func=_cmd_install
    )
    p_uninstall = sub.add_parser(
        "uninstall", help="remove hooks (add --purge to delete the daemon, menu, and all data)"
    )
    p_uninstall.add_argument(
        "--purge",
        action="store_true",
        help="also stop the daemon + menu and delete ~/.hearcode (stems, sessions, logs)",
    )
    p_uninstall.set_defaults(func=_cmd_uninstall)
    p_sim = sub.add_parser("simulate", help="demo a scripted agent session")
    p_sim.add_argument(
        "--scenario",
        choices=_SCENARIOS,
        default="full",
        help="run the whole demo (full) or just one phase",
    )
    p_sim.set_defaults(func=_cmd_simulate)
    sub.add_parser("status", help="check the daemon").set_defaults(func=_cmd_status)

    p_recap = sub.add_parser("recap", help="recap + render the last session")
    p_recap.add_argument("--session", help="path to a .jsonl session log (default: latest)")
    p_recap.add_argument("--out", help="output WAV path (default: alongside the log)")
    p_recap.add_argument("--seconds", type=float, default=30.0, help="recap length")
    p_recap.add_argument("--no-audio", action="store_true", help="skip the WAV render")
    p_recap.add_argument("--no-image", action="store_true", help="skip the waveform SVG")
    p_recap.add_argument("--play", action="store_true", help="play the recap when done (macOS)")
    p_recap.set_defaults(func=_cmd_recap)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
