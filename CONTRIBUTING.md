# Contributing to HearCode

HearCode is an adaptive soundtrack for coding agents — a live, in-terminal score
for Claude Code. It's open source under the [MIT License](LICENSE), and
contributions are welcome: bug reports, docs, new themes and leitmotifs, extra
output adapters, tests, or cross-platform support.

By contributing you agree that your work is licensed under the same MIT terms as
the project (inbound = outbound). There's no CLA to sign. Please be respectful and
constructive in issues and reviews — that's the whole code of conduct.

## Before you start

For anything beyond a small fix, **open an issue first** so we can agree on the
approach before you write code:
<https://github.com/sridharpasala/hearcode/issues>. Small, focused pull requests
are much easier to review and land than large ones.

## Dev setup

> **Python 3.10–3.13** (verified). Avoid 3.14 for now — it may still lack
> prebuilt `sounddevice` / PortAudio wheels, so the audio dependency won't
> install there yet.

Clone the repo and create a virtualenv with an editable install:

```bash
python3 -m venv .venv        # any Python 3.10+
.venv/bin/pip install -e '.[menubar]'
```

The `menubar` extra pulls in `rumps` for the macOS menu bar app; it's **macOS
only**. The core is otherwise portable, but audio playback needs a working
PortAudio (installed automatically with the `sounddevice` wheel on supported
platforms).

Prefer the CLI on your PATH while hacking? Install it editable with
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install --editable .
```

## Running it while you develop

You don't need a live agent to see or hear a change:

```bash
hearcode doctor                      # environment / audio sanity check
hearcode simulate --scenario full    # play the whole emotional arc end to end
hearcode init                        # set up hooks + start the daemon
hearcode menu                        # launch the macOS menu bar app (background)
```

**Audio-asset gotcha:** the stem pack (loops, chimes, leitmotifs) is *synthesized
on first run* into `~/.hearcode/assets/loops/`, then cached. If you edit
`hearcode/adapters/mixer/stem_pack.py`, the cached WAVs won't change until you
regenerate them — delete `~/.hearcode/assets/loops/` (or call `generate()` from
`stem_pack.py`) and **restart the daemon**, since it loads the stems into memory
at startup. Otherwise you'll keep hearing the old sound.

## Where code goes (Clean Architecture)

HearCode follows Clean Architecture — the [ARCHITECTURE.md](ARCHITECTURE.md) doc has
the full layer map. The one rule to internalize is the **Dependency Rule**:
dependencies point inward. The domain knows nothing about audio, HTTP, or macOS;
outer layers depend on the domain, never the reverse.

Where your change belongs:

- **`hearcode/domain/`** — `entities/`, `ports/`, `use_cases/`. **Pure, no I/O.**
  Must not import from `adapters/` or `infrastructure/`. New *behavior* that isn't
  input/output (mood logic, thresholds, arrangement rules) lives here.
- **`hearcode/adapters/`** — implementations behind a port: `mixer/`, `announcer/`,
  `http/`, `recap/`, `session_log/`, `ui/`, `clock/`. A **new output channel**
  (smart lights, desktop notifications, a different synth) is a *new adapter behind
  an existing port* — not a change to the domain.
- **`hearcode/infrastructure/`** — the composition root: `config`, `container`,
  `server`, `daemon`, wiring. This is where everything gets assembled.

Keep the wheel lean: **no bundled binary assets.** Stems are generated at runtime,
not shipped, so please don't add `.wav` files to the package.

## Style

Match the surrounding code:

- Type hints on public functions; `from __future__ import annotations` at the top.
- A short module docstring naming the layer (see existing files for the pattern).
- No new heavyweight dependencies without discussing it in an issue first.

## Tests & verification

There is **no automated test suite yet** — and the pure domain layer is an
excellent place to start one (plain `pytest`, no fixtures or I/O needed).
Contributions that add tests for `hearcode/domain/` are especially welcome.

Until there's a suite, verify changes manually before opening a PR:

```bash
python -m build      # must produce a clean wheel + sdist
hearcode doctor       # runs without errors
hearcode simulate     # audio path still works
```

## Commits & pull requests

- Write commit subjects in the **imperative mood** to match the history
  (e.g. "Make the alert gentler", "Fix: stop was a no-op…").
- In the PR description, say **how you verified** the change (the commands above,
  or what you listened for).

Thanks for helping make coding agents audible. 🎵
