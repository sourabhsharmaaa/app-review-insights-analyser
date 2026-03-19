from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Review(BaseModel):
    """A single Play Store review — userName and title are intentionally absent."""

    review_id: str          # SHA256(text + date) — stable dedup key
    rating: int             # 1–5 stars
    text: str               # review body, min 5 words (enforced at scrape time)
    date: datetime
    thumbs_up: int = 0

    # userName : never modelled — dropped at scrape time (PII gate, layer 1)
    # title    : removed — google-play-scraper has no title field; not useful for analysis


class ScrapedBatch(BaseModel):
    """A dated collection of reviews for one app and one ISO week."""

    app_id: str
    week_label: str         # ISO week label, e.g. "2026-W12"
    scraped_at: datetime
    reviews: List[Review] = Field(default_factory=list)
