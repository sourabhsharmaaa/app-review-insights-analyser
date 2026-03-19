from __future__ import annotations

"""
phase4/combined.py — Phase 4B: Combined JSON model + merge function.

Merges PulseNote (from Phase 3) and FeeExplanation (from Phase 4A)
into a single CombinedReport that is saved as combined_YYYY-WW.json.

This is the canonical output consumed by:
  - Phase 4C (Google Doc append)
  - Phase 4D (Gmail draft creation)
  - Any future integrations (Slack, Notion, etc.)
"""

import logging
import datetime as _dt
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from phase4.fee_scraper import FeeExplanation

logger = logging.getLogger(__name__)


# ── Nested models ─────────────────────────────────────────────────────────────

class ThemeSnapshot(BaseModel):
    """Compact theme representation inside the combined JSON."""
    label: str
    review_count: int
    avg_rating: float
    pct_of_total: float
    one_line_summary: str


class WeeklyPulseSnapshot(BaseModel):
    """Flattened PulseNote fields for the combined JSON schema."""
    week_label: str
    themes: List[ThemeSnapshot]          # top 3 themes
    quotes: List[str]                    # 3 verbatim user quotes
    action_ideas: List[str]              # 3 actionable ideas
    total_reviews_analysed: int
    avg_rating: float


# ── Top-level combined model ──────────────────────────────────────────────────

class CombinedReport(BaseModel):
    """
    The single canonical output that merges weekly pulse + fee explanation.

    Matches the JSON schema specified in ARCHITECTURE.md:
    {
      "date": "2026-03-15",
      "weekly_pulse": { ... },
      "fee_scenario": "Mutual Fund Exit Load",
      "explanation_bullets": [ ... ],
      "source_links": [ ... ],
      "last_checked": "2026-03-15"
    }
    """
    date: _dt.date = Field(default_factory=_dt.date.today)
    weekly_pulse: WeeklyPulseSnapshot
    fee_scenario: str
    explanation_bullets: List[str]
    source_links: List[str]
    last_checked: _dt.date


# ── Public API ────────────────────────────────────────────────────────────────

def combine(pulse: Any, fee: FeeExplanation) -> CombinedReport:
    """
    Merge a PulseNote and FeeExplanation into a CombinedReport.

    Parameters
    ----------
    pulse : PulseNote
        Output from phase3.pulse_builder.build_pulse().
    fee : FeeExplanation
        Output from phase4.fee_scraper.fetch_fee_explanation().

    Returns
    -------
    CombinedReport
        Single object ready to be serialised to combined_YYYY-WW.json.
    """
    pulse_snapshot = WeeklyPulseSnapshot(
        week_label=pulse.week_label,
        themes=[
            ThemeSnapshot(
                label=t.label,
                review_count=t.review_count,
                avg_rating=t.avg_rating,
                pct_of_total=t.pct_of_total,
                one_line_summary=t.one_line_summary,
            )
            for t in pulse.top_themes
        ],
        quotes=pulse.user_quotes,
        action_ideas=pulse.action_ideas,
        total_reviews_analysed=pulse.total_reviews_analysed,
        avg_rating=pulse.avg_rating,
    )

    combined = CombinedReport(
        date=_dt.date.today(),
        weekly_pulse=pulse_snapshot,
        fee_scenario=fee.scenario,
        explanation_bullets=fee.bullets,
        source_links=fee.source_links,
        last_checked=fee.last_checked,
    )

    logger.info(
        "CombinedReport built — week: %s | %d themes | %d fee bullets | %d source links",
        pulse.week_label,
        len(pulse_snapshot.themes),
        len(fee.bullets),
        len(fee.source_links),
    )
    return combined
