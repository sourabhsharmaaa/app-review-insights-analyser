from __future__ import annotations

"""
phase1/play_store.py — Play Store review scraper (canonical implementation).
scraper/play_store.py imports from here.

Key design decisions:
- Date cutoff computed at call time: datetime.now(UTC) - timedelta(weeks=weeks_back)
- userName is NEVER stored — dropped here before constructing Review objects
- title is NOT stored — not provided by google-play-scraper; not useful for analysis
- Reviews with fewer than min_review_words words are discarded at collection time
- max_reviews cap applies to USABLE reviews (after word-count filter)
- Randomly samples down to max_reviews preserving rating distribution
- tenacity retries around each HTTP call (exp backoff, 5 attempts max)
"""

import hashlib
import logging
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.models import Review

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200        # google-play-scraper max per page
_BUFFER_MULT = 3        # collect up to 3× max before sampling for better distribution
_MIN_ASCII_RATIO = 0.80 # reviews where <80% of alpha chars are ASCII are non-English


def _is_english(text: str) -> bool:
    """
    Returns True if ≥80% of alphabetic characters are ASCII (Latin script).
    Filters out Hindi, Tamil, Marathi, Bengali and other Indian-language reviews.
    No external dependency — uses only Unicode code points.
    """
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return False
    ascii_count = sum(1 for c in alpha_chars if ord(c) < 128)
    return (ascii_count / len(alpha_chars)) >= _MIN_ASCII_RATIO


def _make_review_id(text: str, date: datetime) -> str:
    """SHA256(text + ISO-date) → stable 16-char hex ID."""
    raw = f"{text.strip()}{date.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _sample_by_rating(reviews: List[Review], n: int) -> List[Review]:
    """
    Randomly sample n reviews while preserving rating distribution.
    Each star bucket (1–5) gets a proportional share of the sample.
    """
    if len(reviews) <= n:
        return reviews

    by_rating: Dict[int, List[Review]] = defaultdict(list)
    for r in reviews:
        by_rating[r.rating].append(r)

    total = len(reviews)
    sampled: List[Review] = []
    for bucket in by_rating.values():
        share = max(1, round(n * len(bucket) / total))
        shuffled = list(bucket)
        random.shuffle(shuffled)
        sampled.extend(shuffled[:share])

    random.shuffle(sampled)
    return sampled[:n]


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _fetch_page(
    app_id: str,
    count: int,
    continuation_token: Optional[str],
):
    """Single paginated request to google-play-scraper, wrapped in tenacity retry."""
    from google_play_scraper import Sort
    from google_play_scraper import reviews as gps_reviews

    result, next_token = gps_reviews(
        app_id,
        lang="en",
        country="in",
        sort=Sort.NEWEST,
        count=count,
        continuation_token=continuation_token,
    )
    return result, next_token


def fetch_reviews(
    app_id: str,
    weeks_back: int = 12,
    max_reviews: int = 2000,
    min_review_words: int = 5,
) -> List[Review]:
    """
    Fetch Play Store reviews for `app_id` from the last `weeks_back` weeks.

    Filtering rules (applied at collection time):
    - Reviews with fewer than min_review_words words are discarded as noise
    - userName is intentionally NEVER extracted or stored (PII gate)
    - title is not stored (not available from google-play-scraper)

    Sampling:
    - max_reviews cap applies to USABLE reviews (after word-count filter)
    - If usable reviews exceed max_reviews, sample down preserving rating distribution
    """
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)
    logger.info(
        "Fetching reviews | app=%s | cutoff=%s | max_usable=%d | min_words=%d",
        app_id, cutoff.strftime("%Y-%m-%d"), max_reviews, min_review_words,
    )

    collected: List[Review] = []
    discarded_short = 0
    discarded_non_english = 0
    continuation_token: Optional[str] = None
    page = 0

    while True:
        page += 1
        logger.debug("Page %d — usable so far: %d", page, len(collected))

        try:
            raw_batch, continuation_token = _fetch_page(
                app_id, count=_PAGE_SIZE, continuation_token=continuation_token
            )
        except Exception as exc:
            logger.warning("Play Store fetch failed after retries: %s", exc)
            break

        if not raw_batch:
            logger.debug("Empty page — stopping pagination")
            break

        stop_early = False
        for raw in raw_batch:
            # ── PII gate: userName is never touched ──────────────────────────
            review_date: datetime = raw.get("at") or datetime.now(timezone.utc)
            if review_date.tzinfo is None:
                review_date = review_date.replace(tzinfo=timezone.utc)

            if review_date < cutoff:
                logger.debug("Date cutoff reached at %s — stopping", review_date.date())
                stop_early = True
                break

            text: str = (raw.get("content") or "").strip()

            # ── Word-count filter: discard noise reviews ──────────────────────
            if len(text.split()) < min_review_words:
                discarded_short += 1
                continue

            # ── Language filter: English only ─────────────────────────────────
            if not _is_english(text):
                discarded_non_english += 1
                continue

            collected.append(Review(
                review_id=_make_review_id(text, review_date),
                rating=int(raw.get("score", 3)),
                text=text,
                date=review_date,
                thumbs_up=int(raw.get("thumbsUpCount", 0)),
            ))

            if len(collected) >= max_reviews * _BUFFER_MULT:
                logger.debug("Buffer (%d usable) reached — stopping pagination",
                             max_reviews * _BUFFER_MULT)
                stop_early = True
                break

        if stop_early or not continuation_token:
            break

    logger.info(
        "Collected %d usable reviews | discarded %d (< %d words) | discarded %d (non-English) | target: %d",
        len(collected), discarded_short, min_review_words, discarded_non_english, max_reviews,
    )

    if not collected:
        return []

    result = _sample_by_rating(collected, max_reviews)
    logger.info("Returning %d reviews after rating-stratified sampling", len(result))
    return result
