from __future__ import annotations

# Delegates to phase2/deduplicator.py — canonical implementation lives there.
# See phase2/deduplicator.py for full implementation details.

from phase2.deduplicator import deduplicate  # noqa: F401

__all__ = ["deduplicate"]
