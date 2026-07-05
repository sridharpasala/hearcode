# CLAUDE.md — HearCode

Guidance for working in this repo. HearCode is an **adaptive soundtrack for coding
agents**: a background daemon turns a live stream of an agent's tool calls
(Claude Code hooks, or any producer) into layered, mood-reflecting audio + spoken
alerts. Published on PyPI as `hearcode`; public repo `sridharpasala/hearcode`.

> History: renamed CodeMuz → CodeMuse → **HearCode** before the first PyPI release
> (earlier names were blocked/taken on PyPI). This `hearcode/` directory is the
> single working dir; an old `../CodeMuz` directory is a frozen pre-rename archive —
> don't develop there.

## Architecture — Clean Architecture (dependencies point inward)

```
hearcode/
  domain/          pure core, stdlib only — never imports adapters/infrastructure
    entities/      Intent, AgentEvent, MusicalState, SessionState, SessionEntry
    ports/         IAudioMixer, IAnnouncer, ISessionLog, IClock (abstractions)
    use_cases/     HandleAgentEventUseCase, MarkIdleUseCase
  adapters/        implementations behind a port
    http/          EventController (hook JSON -> AgentEvent)
    mixer/         SounddeviceMixer (real), NullMixer; arrangement + stem_pack (synth)
    announcer/     SayAnnouncer (macOS TTS), NullAnnouncer
    session_log/   JsonlSessionLog, NullSessionLog
    recap/         RecapRenderer (audio), WaveformExporter (SVG poster)
    ui/            HearCodeApp (macOS menu bar, rumps — optional)
    clock/         SystemClock
  infrastructure/  composition root: config, container (DI), server (HTTP+idle),
                   installer (hooks), daemon + menu_app (detached lifecycle)
```

**The Dependency Rule is the one hard rule.** Domain is pure and I/O-free. A new
output channel (lights, notifications, a different synth) is a *new adapter behind
an existing port*, not a domain change. Every output port has a `Null*` fallback so
the system runs headless/silent unchanged.

## Runtime model

A long-lived local **daemon** listens on `127.0.0.1:8420`. Claude Code hooks fire a
fire-and-forget `curl` per event to `POST /event`. Control plane (all local):
`GET /health`, `GET /state`, `POST /event`, `POST /theme`, `POST /voice`,
`POST /pad`, `POST /shutdown`. Audio is a sounddevice callback mixer (per-stem gain
crossfades) with a soft-knee limiter + `HEARCODE_VOLUME` master ceiling.

## Dev setup

Python **3.10–3.13** (verified; avoid 3.14 — audio wheels). This repo has a `.venv`:

```bash
.venv/bin/python -m hearcode doctor      # or activate the venv first
# fresh: python3 -m venv .venv && .venv/bin/pip install -e '.[menubar]'
```

The `menubar` extra (`rumps`) is macOS-only. The installed CLI is `hearcode`
(`uv tool install --editable '.[menubar]'` re-points the global command here).

## Common commands

```bash
hearcode init        # one-step: synth stems + install hooks + start daemon + menu
hearcode simulate    # scripted demo session (no agent needed) — good for hearing changes
hearcode doctor      # ✓/✗ env report (python, audio, stems, hooks, daemon)
hearcode start|stop  # daemon lifecycle (start is background; -f to attach)
hearcode theme uplift | hearcode pad airy | hearcode voice Daniel   # live control
hearcode menu        # macOS menu bar app (background)
hearcode recap       # session stats + recap.wav + recap.svg poster
hearcode uninstall --purge   # remove hooks + daemon/menu + ~/.hearcode data
```

**Audio-asset gotcha:** stems are synthesized on first run into
`~/.hearcode/assets/loops/`, then cached. After editing
`hearcode/adapters/mixer/stem_pack.py`, delete that dir (or re-run `generate()`)
**and restart the daemon** — it loads stems into memory at startup.

## Config / env

`~/.hearcode/` holds generated assets, session logs, pidfiles. Env vars (read only
in `infrastructure/config.py`): `HEARCODE_PORT`, `HEARCODE_THEME`, `HEARCODE_PAD`,
`HEARCODE_VOICE`, `HEARCODE_VOLUME`, `HEARCODE_SILENT`, `HEARCODE_LEITMOTIFS`,
`HEARCODE_ANNOUNCE`, `HEARCODE_RECORD`, `HEARCODE_ASSETS`.

## Tests & verification

No automated test suite yet — the pure `domain/` is the place to start one (plain
pytest). Until then verify manually: `python -m build` must be clean, and
`hearcode doctor` + `hearcode simulate` should run without errors. When changing
audio, listen via `hearcode simulate --scenario full`.

## Release process (SemVer; PyPI + GitHub)

1. Bump `hearcode/__init__.py` `__version__` + add a `CHANGELOG.md` entry.
2. `.venv/bin/python -m build .` → wheel + sdist in `dist/`; `twine check dist/*`.
3. `twine upload dist/*` (needs a real PyPI token — `TWINE_USERNAME=__token__`).
4. Tag `vX.Y.Z`, push, and `gh release create vX.Y.Z dist/* --repo sridharpasala/hearcode`.
   - PyPI versions are immutable — never reuse a number.

## Style

Match surrounding code: type hints, `from __future__ import annotations`, a module
docstring naming the layer. No bundled binary assets (stems are generated). No new
heavy dependencies without discussion.
