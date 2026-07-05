# Changelog

All notable changes to HearCode are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.2] — 2026-07-05

### Fixed
- `hearcode doctor` hardcoded "needs ≥ 3.13" and reported a failing ✗ on Python
  3.10–3.12 even though those are supported. Align the check with the real floor
  (≥ 3.10).

## [0.1.1] — 2026-07-05

### Changed
- Lower the supported Python floor from `>=3.13` to **`>=3.10`** so the 3.10–3.12
  majority can `pip install hearcode` without an interpreter-version error.
  Verified compile + import + runtime smoke on 3.10, 3.11, 3.12, and 3.13.

## [0.1.0] — 2026-07-05

Initial public release. **Hear your coding agent work** — an adaptive soundtrack
that reflects what Claude Code (or any hook-capable agent) is doing.

### Added
- Adaptive mood bed (explore / build / action / tension / error) with intensity scaling.
- Per-tool leitmotifs; "agent needs you" spoken alerts (macOS `say`).
- Build-health harmony (tests green/red) and stuck-loop detection.
- Themes (`focus`, `uplift`) and ambience (`low_warm`, `open_fifths`, `detuned_soft`,
  `airy`, `classic`) — both switchable live.
- macOS menu bar app; session recap + shareable waveform poster (SVG).
- Drive from any agent via a local `POST /event`; one-command `hearcode init`;
  full removal via `hearcode uninstall --purge`.

### Security / robustness
- HTTP server binds `127.0.0.1` only; POST bodies capped (413 over 64 KB).
- Soft-knee audio limiter, concurrent-accent cap, and `HEARCODE_VOLUME` ceiling.

[0.1.2]: https://github.com/sridharpasala/hearcode/releases/tag/v0.1.2
[0.1.1]: https://github.com/sridharpasala/hearcode/releases/tag/v0.1.1
[0.1.0]: https://github.com/sridharpasala/hearcode/releases/tag/v0.1.0
