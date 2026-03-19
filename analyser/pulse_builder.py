from __future__ import annotations

# Delegates to phase3/pulse_builder.py — canonical implementation lives there.
# ThemeSummary and PulseNote are also re-exported here because storage/cache.py
# and pipeline/runner.py import them from this path.
from phase3.pulse_builder import (  # noqa: F401
    ThemeSummary,
    PulseNote,
    build_pulse,
)

__all__ = ["ThemeSummary", "PulseNote", "build_pulse"]
