# HearCode 🎵

[![PyPI](https://img.shields.io/pypi/v/hearcode.svg)](https://pypi.org/project/hearcode/)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)

**An adaptive soundtrack for coding agents.** While Claude Code (or any agent
that can run hooks) works, HearCode plays music that reflects what it's doing —
exploring sounds different from writing code, which sounds different from running
commands, hitting an error, or finishing. You can *hear* whether the agent is
busy, stuck, or done — even with the terminal in the background.

It's video-game adaptive music for your terminal: a handful of looping stems that
crossfade in and out based on a live stream of the agent's tool calls.

<p align="center">
  <img src="https://raw.githubusercontent.com/sridharpasala/hearcode/main/docs/recap-example.svg" alt="HearCode session recap poster — a waveform coloured by the agent's mood, with markers where it erred, got stuck, or needed you" width="840">
  <br>
  <sub><em>Every session becomes a shareable poster — a waveform coloured by what the agent was doing
  (blue exploring · green building · amber running · red erroring), with markers where it got stuck or needed you.</em></sub>
</p>

## Features

- 🎚️ **Adaptive mood bed** — exploring, building, running, erroring, and finishing each sound distinct; the groove thickens as the agent works harder.
- 🎺 **Per-tool leitmotifs** — a short signature per tool family, so you can tell Read from Edit from Bash by ear alone.
- 🔔 **"Agent needs you" alerts** — when it blocks on a permission, the music ducks, a chime plays, and macOS *speaks* what it needs.
- 🟢 **Build-health harmony** — passing tests brighten the tonality; failures darken it, and it persists so you always know if the build is green.
- 🌀 **Stuck-loop detection** — a rising drone and alert when the agent spins on the same thing.
- 🎨 **Live themes & ambience** — swap the whole vibe, or just the pad texture, with no restart or gap.
- 📼 **Shareable recap poster** — every session exports the waveform SVG above, coloured by mood.
- 🎛️ **macOS menu bar app** — start/stop, theme, ambience, and alert-voice, plus a live mood glyph.
- 🔌 **Any agent, one POST** — not Claude-only; drive it from Cursor, a CI step, or your own SDK agent.
- 🧩 **Pure-synth, zero downloads** — stems are generated on first run (CC0), so the install is tiny and works offline.

## How it works

```
Claude Code hook ──curl (JSON, <50ms)──▶ HearCode daemon ──▶ layered audio + TTS
 (PreToolUse, …)                          (state machine + stem mixer)  ──▶ session log
```

| Agent activity        | What you hear                         |
|-----------------------|---------------------------------------|
| Read / Grep / Glob    | calm ambient pad (exploring)          |
| Edit / Write          | bass + drums kick in (building)       |
| Bash / Task           | lead joins, fuller groove (action)    |
| a tool fails          | dissonant sting                       |
| busier work           | groove gets louder/denser (intensity) |
| stuck in a doom loop   | uneasy drone creeps in + a "stuck" alert |
| needs you (permission / waiting) | unmissable chime + spoken alert |
| agent finishes (Stop) | resolve chord, then silence           |
| agent goes quiet      | music stops — it returns when activity resumes |
| every tool call       | a per-tool **leitmotif** plays on top |

### Leitmotifs 🎺

Over the mood bed, each tool call triggers a short signature so you can tell
*which* tool the agent reached for — by ear alone:

| Tool family                         | Signature                       |
|-------------------------------------|---------------------------------|
| Read / NotebookRead                 | soft marimba pluck              |
| Grep / Glob / LS / ToolSearch       | two quick **rising** notes      |
| Edit / Write / MultiEdit / …        | two **falling** piano notes     |
| Bash                                | percussive tom thump            |
| WebFetch / WebSearch                | bright bell chime               |
| Task / Agent / Skill (subagents)    | warm horn swell                 |

A short per-tool cooldown keeps rapid repeats musical. Disable with
`HEARCODE_LEITMOTIFS=0` or `Config(leitmotifs=False)`.

### "Agent needs you" alert 🔔🗣️

When the agent blocks waiting on you (a `Notification`, a `PermissionRequest`, or
a `PermissionDenied`), HearCode ducks the music, plays an unmissable chime, and —
on macOS — *speaks* a short summary via `say` (e.g. "Claude needs permission to
use Bash"). Walk away during a long autonomous run and it'll call you back.

Speech is a separate output adapter (`IAnnouncer` → `SayAnnouncer`), independent
of the music. Disable speech with `HEARCODE_ANNOUNCE=0`; pick a voice with
`HEARCODE_VOICE="Daniel"`, or switch it **live** while the daemon runs:

```bash
hearcode voice            # show the current voice
hearcode voice --list     # every macOS voice installed (~180: names + languages)
hearcode voice Daniel     # switch the alert voice on the fly
hearcode voice default    # back to the system default
```

The menu bar app has the same choices under **Alert voice**, and *previews* each
one aloud when you pick it.

### Build-health harmony 🟢🔴

A slow-moving harmonic color tracks whether the code is currently green or red.
When the agent runs tests / a build / a linter (`pytest`, `go test`, `npm test`,
`cargo build`, `tsc`, `ruff`, …), the outcome moves a `health` value: passes
brighten the harmony toward a major Eb shimmer, failures darken it toward a low
tritone drone. It persists across the session — a green build stays green while
the agent rests — so the *tonality* tells you the state of the build even when
nothing is happening.

### Themes 🎨

The continuous bed comes in two flavours — pick the mood that fits how you work:

| Theme    | Feel                              | Sound                                            |
|----------|-----------------------------------|--------------------------------------------------|
| `focus`  | heads-down, pensive (default)     | C-minor pad, kick-driven groove                  |
| `uplift` | positive, "good going", in flow   | bright Eb-major pad, shaker + handclap groove    |

Pick the starting theme with `HEARCODE_THEME`, or switch it **live** (no restart,
no gap) while the daemon runs:

```bash
HEARCODE_THEME=uplift hearcode start   # start on the sunnier bed
hearcode theme                        # show the current theme + the available ones
hearcode theme uplift                 # crossfade to a different bed on the fly
```

A theme only reskins the **mood bed** (`pad`/`bass`/`drums`/`lead`) — the alerts,
leitmotifs, stuck-loop drone, and build-health harmony are identical across
themes, so everything still maps the same way (Eb major is C minor's relative
major, so they share a key signature and stay in tune). Adding a new theme is
just four more synthesized stems in `tools/gen_stems.py`.

### Ambience 🌫️

The **pad** is the sustained bed that plays under everything (and, while you're
just exploring, *is* the whole soundtrack). Its texture is selectable
independently of the theme, so you can dial how present or invisible the bed
feels — handy if the default is too much for long, heads-down sessions:

| Ambience       | Feel                                             |
|----------------|--------------------------------------------------|
| `low_warm`     | low, detuned, no pulse — sits *under* the work (default) |
| `open_fifths`  | root + fifth, spacious and neutral               |
| `detuned_soft` | the full triad's colour, but warm and still      |
| `airy`         | just root + fifth, quiet, near-invisible         |
| `classic`      | the original present triad with a slow tremolo   |

Each style stays in key in both themes. Switch it **live** (seamless — only the
pad crossfades, the groove keeps playing), via the menu bar **Ambience** submenu,
the CLI, or the starting default:

```bash
HEARCODE_PAD=airy hearcode start   # start on a near-invisible bed
hearcode pad                      # show the current ambience + the available ones
hearcode pad open_fifths          # swap the pad texture on the fly
```

### Session recap 📼🌊

Every musical moment is recorded to a per-session log
(`~/.hearcode/sessions/<timestamp>.jsonl`). Afterward, `hearcode recap` prints a
summary of the session and re-renders it as a **time-compressed audio highlight
reel** plus a **shareable waveform poster** (SVG) whose colour at each instant is
the agent's mood:

```bash
python -m hearcode recap            # stats + a recap.wav + a recap.svg of the last session
python -m hearcode recap --play     # …and play the audio when it's done (macOS)
python -m hearcode recap --no-audio # stats + image only
```

```
♪ HearCode session recap — 20260630-073250.jsonl
  70 moments over 405s of work
  build  ██████  28     action  ██  12     explore  █  6     idle  █  5
  busiest tools: Edit×24, Bash×17, Write×6
  errors: 4 · stuck alerts: 1 · needs-you alerts: 5
  peak intensity 1.00 · peak anxiety 1.00 · ended neutral
```

The poster is pure SVG (no image dependency) — a waveform coloured by intent with
glyph markers where errors / stuck / needs-you alerts fired. It's the share-native
artifact for streamers and demos. The live mixer and the offline renderer share
one arrangement module, so a recap is a faithful fast-forward of what you heard.
Disable recording with `HEARCODE_RECORD=0`.

## Install

One line with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/)
puts `hearcode` on your PATH:

```bash
uv tool install hearcode       # or: pipx install hearcode
```

HearCode needs **Python 3.10 or newer** (3.14 may still lack audio wheels);
uv/pipx pick a matching interpreter for you.

> **From source** (for development):
>
> ```bash
> git clone https://github.com/sridharpasala/hearcode && cd hearcode
> python3.13 -m venv .venv && source .venv/bin/activate
> pip install -e .
> ```
>
> From a source checkout the command is `python -m hearcode …`; an installed
> package (uv/pipx/pip) gives you plain `hearcode`.

## Quick start

```bash
hearcode init       # synthesize stems + install hooks + start the daemon (one step)
hearcode simulate   # hear a scripted demo session (no agent needed)
```

That's the whole setup — `hearcode init` synthesizes the stem pack (CC0, no
downloads) into `~/.hearcode/assets/loops/<theme>/`, wires the hooks into
`~/.claude/settings.json`, starts the daemon in the background, and — on macOS
with the `menubar` extra — brings up the menu bar app automatically. Now just use
Claude Code normally and you'll hear it.

> The menu bar app auto-launches only if `rumps` is installed
> (`uv tool install 'hearcode[menubar]'`); otherwise `init` prints a one-line hint
> and carries on. Skip it for a run with `hearcode init --no-menu`.

Manage the daemon:

```bash
hearcode start              # start the daemon in the background (without the full init)
hearcode doctor             # ✓/✗ report: python, audio, stems, hooks, daemon
hearcode theme uplift       # switch the soundtrack theme live (no restart)
hearcode voice Daniel       # switch the spoken-alert voice live (--list for all)
hearcode stop               # stop the background daemon
hearcode start --foreground # run attached instead (Ctrl-C to quit)
hearcode uninstall          # remove the Claude Code hooks
hearcode uninstall --purge  # …and stop the daemon/menu + delete ~/.hearcode (full removal)
```

### Menu bar app (macOS) 🎛️

Prefer not to touch a terminal? A tiny menu bar app puts Start/Stop, live theme
and ambience switching, alert-voice selection, and the agent's current mood in
your top menu — the glyph changes with what the agent is doing (🔍 explore ·
🔨 build · ⚡ action · 🔔 needs you · ✅ done):

```bash
uv tool install 'hearcode[menubar]'   # adds the (macOS-only) rumps dependency
hearcode init                         # …now auto-launches the menu bar app too
```

With the extra installed, `hearcode init` starts the app for you — the icon just
appears. To (re)launch it by hand it always runs in the background: `hearcode menu`
to start it, `hearcode menu --stop` to stop it. It's a menu bar accessory — a
status item only, no Dock icon.

It's a thin client over the daemon — start/stop, pick a theme, set the ambience,
choose the alert voice, play the demo, or run doctor, all from the menu. The daemon keeps running
if you quit the app.

Point the stem pack elsewhere with `HEARCODE_ASSETS=/path`, rebuild it anytime with
`python tools/gen_stems.py`, or run headless with `hearcode start -f --silent`
(attached, logging the soundtrack decisions instead of playing them).

## Drive it from any agent

HearCode isn't Claude-Code-specific — the daemon listens for one thing:
`POST http://127.0.0.1:8420/event`. Claude Code's hooks are just one producer.
Cursor, a CI step, or your own SDK agent can score the same soundtrack by POSTing
`{"hook_event_name": "…", "tool_name": "…", "tool_input": {…}}` when they act.
See **[INTEGRATE.md](INTEGRATE.md)** for the full wire contract — the event table,
error detection, response shape, and copy-paste `curl`/Python examples.

## Architecture (Clean Architecture)

Dependencies point inward; the domain knows nothing about audio, HTTP, or files.

```
hearcode/
  domain/          pure core — stdlib only
    entities/      Intent, AgentEvent, MusicalState, SessionState, SessionEntry
    ports/         IAudioMixer, IAnnouncer, ISessionLog, IClock
    use_cases/     HandleAgentEventUseCase, MarkIdleUseCase
  adapters/        translation layer
    http/          EventController  (hook JSON -> AgentEvent, humble object)
    mixer/         SounddeviceMixer (real), NullMixer (null); arrangement +
                   stem_pack (synthesizes the themed stem packs on first run)
    announcer/     SayAnnouncer (macOS TTS), NullAnnouncer
    session_log/   JsonlSessionLog, NullSessionLog
    recap/         RecapRenderer (offline audio), WaveformExporter (SVG)
    ui/            HearCodeApp (macOS menu bar controller — optional, driving)
    clock/         SystemClock
  infrastructure/  composition root
    config, container (DI), server (HTTP + idle timer), installer (hooks),
    daemon + menu_app (background start/stop via a pidfile)
tools/gen_stems.py thin shim → stem_pack.generate() for contributors
```

Swapping the audio engine, the transport, the announcer, or the stem pack each
touches exactly one adapter — the domain and use cases never change. Every output
port has a Null implementation, so the system runs unchanged with no audio device,
no TTS, or recording off.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full layering, runtime
topology, and per-flow sequence diagrams, and **[INTEGRATE.md](INTEGRATE.md)** for
the `POST /event` contract to drive HearCode from any agent.

## Status

V1 MVP + per-tool leitmotifs + stuck-loop detection + "agent needs you" alert +
build-health harmony + session recap & shareable waveform export. Roadmap:
intensity → tempo, alternate output adapters (smart lights, desktop notifications),
PNG/animated recap export, packaging as a shareable Claude Code plugin,
Linux/Windows audio.
