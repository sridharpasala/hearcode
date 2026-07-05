"""Layer 3 — driving UI adapters (a macOS menu bar controller).

These are *inbound* adapters: like the Claude Code hooks, they drive HearCode from
the outside. The menu bar app is a thin client over the same daemon surface
(`/state`, `/theme`) plus the daemon lifecycle helpers — it holds no business
logic and is entirely optional (guarded behind the `menubar` extra).
"""
