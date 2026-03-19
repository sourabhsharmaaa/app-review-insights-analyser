from __future__ import annotations

"""
phase2/deduplicator.py — SHA256-based deduplication (canonical implementation).
processor/deduplicator.py imports from here.

review_id = SHA256(text + date) computed in phase1/play_store.py.
Dedup matters when scrape windows overlap across consecutive weekly runs —
the same review can appear in both the week-11 and week-12 scrape.
"""

import logging
from typing import List

from scraper.models import Review

logger = logging.getLogger(__name__)


def deduplicate(reviews: List[Review]) -> List[Review]:
    """
    Remove duplicate reviews by review_id.
    Maintains insertion order — first occurrence of each ID wins.
    """
    seen: set = set()
    unique: List[Review] = []

    for r in reviews:
        if r.review_id not in seen:
            seen.add(r.review_id)
            unique.append(r)

    removed = len(reviews) - len(unique)
    if removed:
        logger.info(
            "Deduplication removed %d duplicate reviews (%d → %d)",
            removed, len(reviews), len(unique),
        )
    return unique
