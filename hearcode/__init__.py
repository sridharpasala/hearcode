"""HearCode — an adaptive soundtrack for coding agents.

Architecture (Clean Architecture, dependencies point inward):

    domain/         Layer 1 entities + 1b ports + Layer 2 use cases (pure, stdlib only)
    adapters/       Layer 3 — HTTP controller, audio mixers, clock
    infrastructure/ Layer 4 — config, DI container, HTTP server, hook installer
"""

__version__ = "0.1.0"
