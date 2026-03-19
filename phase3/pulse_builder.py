from __future__ import annotations

"""
phase3/pulse_builder.py — LLM Call 3 + PulseNote model (canonical implementation).
analyser/pulse_builder.py imports from here.

Takes theme-grouped reviews → produces a validated PulseNote JSON.
~1,500 tokens total — safe under Groq 6,000 TPM free tier.
Retries once on Pydantic validation failure with a corrective prompt.
Falls back to a rule-based pulse (counts + ratings only) after 2 failures.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field, ValidationError

from scraper.models import Review

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are writing a weekly product health pulse for a fintech app called GROWW. "
    "Be concise, specific, and evidence-based. "
    "Never invent information not present in the reviews provided. "
    "Keep the entire note under 250 words — count all one_line_summary fields and action_ideas combined."
)


# ── Pydantic models ────────────────────────────────────────────────────────────

class ThemeSummary(BaseModel):
    label: str
    review_count: int
    avg_rating: float
    pct_of_total: float
    one_line_summary: str       # max 15 words, specific to GROWW users


class PulseNote(BaseModel):
    week_label: str
    top_themes: List[ThemeSummary]      # exactly 3
    user_quotes: List[str]              # exactly 3, verbatim (PII already scrubbed)
    action_ideas: List[str]             # exactly 3, specific and actionable
    total_reviews_analysed: int
    avg_rating: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _top3_stats(
    themed: Dict[str, List[Review]],
) -> Tuple[List[Tuple[str, List[Review]]], int, float]:
    """Return (top-3 themes sorted by count, total reviews, overall avg rating)."""
    total = sum(len(v) for v in themed.values())
    sorted_themes = sorted(themed.items(), key=lambda kv: len(kv[1]), reverse=True)[:3]
    all_ratings = [r.rating for reviews in themed.values() for r in reviews]
    avg = round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else 0.0
    return sorted_themes, total, avg


def _build_prompt(
    top3: List[Tuple[str, List[Review]]],
    total: int,
    schema: str,
    corrective: bool = False,
) -> str:
    blocks = []
    for label, reviews in top3:
        avg_r = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0.0
        pct   = round(len(reviews) / total * 100, 1)
        samples = [f'    - "{r.text[:200]}"' for r in reviews[:3]]
        blocks.append(
            f"Theme: {label}\n"
            f"  Count: {len(reviews)} reviews ({pct}% of total) | Avg rating: {avg_r}★\n"
            f"  Sample reviews:\n" + "\n".join(samples)
        )

    prefix = "Your previous response did not match the required JSON schema. Try again.\n\n" if corrective else ""
    return (
        f"{prefix}Given these theme statistics from {total} total GROWW app reviews, "
        "generate a PulseNote JSON with:\n"
        "- one_line_summary per theme (max 15 words, specific to what users said)\n"
        "- 3 user_quotes: copy verbatim sentences from the sample reviews above — NO paraphrasing\n"
        "- 3 action_ideas: specific, evidence-grounded, actionable for the product team (max 30 words each)\n"
        "- IMPORTANT: total word count across all one_line_summary fields and action_ideas must be ≤250 words\n"
        f"Return ONLY valid JSON matching this schema:\n{schema}\n\n"
        "Theme data:\n" + "\n\n".join(blocks)
    )


_WORD_LIMIT = 250


def _count_pulse_words(pulse: PulseNote) -> int:
    """Count generated words: all one_line_summary fields + all action_ideas."""
    summaries = " ".join(t.one_line_summary for t in pulse.top_themes)
    actions   = " ".join(pulse.action_ideas)
    return len((summaries + " " + actions).split())


def _word_count_corrective(pulse: PulseNote) -> str:
    actual = _count_pulse_words(pulse)
    return (
        f"Your response was {actual} words in the one_line_summary and action_ideas fields. "
        f"Shorten to ≤{_WORD_LIMIT} words total across those fields. "
        "Keep one_line_summary ≤15 words each and action_ideas ≤30 words each. "
        "Return the same JSON structure with shorter text."
    )


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        raw = raw.lstrip("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _rule_based_fallback(
    top3: List[Tuple[str, List[Review]]],
    week_label: str,
    total: int,
    avg_rating: float,
) -> PulseNote:
    """Minimal pulse built from counts + ratings — no LLM required."""
    themes = [
        ThemeSummary(
            label=label,
            review_count=len(reviews),
            avg_rating=round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 0.0,
            pct_of_total=round(len(reviews) / total * 100, 1) if total else 0.0,
            one_line_summary=f"{len(reviews)} users flagged this as a recurring concern.",
        )
        for label, reviews in top3
    ]
    quotes = [r.text[:150] for r in top3[0][1][:3]] if top3 else ["No quote available."] * 3
    while len(quotes) < 3:
        quotes.append("No quote available.")

    return PulseNote(
        week_label=week_label,
        top_themes=themes,
        user_quotes=quotes[:3],
        action_ideas=[
            f"Investigate '{top3[0][0]}' — highest review volume this week.",
            f"Review '{top3[1][0]}' user feedback for quick wins." if len(top3) > 1 else "Audit app stability.",
            "Respond publicly to top negative reviews to show responsiveness.",
        ],
        total_reviews_analysed=total,
        avg_rating=avg_rating,
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def build_pulse(
    themed_reviews: Dict[str, List[Review]],
    week_label: str,
    client,
) -> PulseNote:
    """
    LLM Call 3: produce the final PulseNote from theme-grouped reviews.

    Model : llama-3.3-70b-versatile
    Temp  : 0.4
    ~1,500 tokens — safe under Groq 6,000 TPM free tier.
    Validates output against PulseNote Pydantic schema.
    Retries once on validation failure.
    Falls back to rule-based pulse after 2 failures.
    """
    model  = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    top3, total, avg_rating = _top3_stats(themed_reviews)

    if not top3:
        logger.warning("No themed reviews — returning empty fallback pulse")
        return _rule_based_fallback([], week_label, 0, 0.0)

    schema = json.dumps({
        "week_label": "string",
        "top_themes": [
            {"label": "string", "review_count": 0, "avg_rating": 0.0,
             "pct_of_total": 0.0, "one_line_summary": "string"}
        ],
        "user_quotes":   ["string", "string", "string"],
        "action_ideas":  ["string", "string", "string"],
        "total_reviews_analysed": 0,
        "avg_rating": 0.0,
    }, indent=2)

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": _build_prompt(top3, total, schema, corrective=(attempt > 0))},
                ],
                temperature=0.4,
                max_tokens=1024,
            )
            raw     = response.choices[0].message.content or ""
            payload = _parse_json(raw)

            if payload is None:
                logger.warning("Attempt %d — could not parse JSON from LLM response", attempt + 1)
                continue

            # Overwrite LLM numbers with ground-truth computed stats
            payload["week_label"]              = week_label
            payload["total_reviews_analysed"]  = total
            payload["avg_rating"]              = avg_rating

            for i, (label, reviews) in enumerate(top3):
                if i < len(payload.get("top_themes", [])):
                    t = payload["top_themes"][i]
                    t["label"]        = label
                    t["review_count"] = len(reviews)
                    t["avg_rating"]   = round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 0.0
                    t["pct_of_total"] = round(len(reviews) / total * 100, 1) if total else 0.0

            pulse = PulseNote.model_validate(payload)

            # Post-validation word count check
            word_count = _count_pulse_words(pulse)
            if word_count > _WORD_LIMIT:
                logger.warning(
                    "Attempt %d — pulse is %d words (limit %d); retrying with word-count corrective",
                    attempt + 1, word_count, _WORD_LIMIT,
                )
                if attempt == 0:
                    # Inject corrective into next attempt via a second immediate call
                    corrective_response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system",    "content": _SYSTEM_PROMPT},
                            {"role": "user",      "content": _build_prompt(top3, total, schema)},
                            {"role": "assistant", "content": raw},
                            {"role": "user",      "content": _word_count_corrective(pulse)},
                        ],
                        temperature=0.3,
                        max_tokens=1024,
                    )
                    raw2     = corrective_response.choices[0].message.content or ""
                    payload2 = _parse_json(raw2)
                    if payload2 is not None:
                        payload2["week_label"]             = week_label
                        payload2["total_reviews_analysed"] = total
                        payload2["avg_rating"]             = avg_rating
                        for i, (label, reviews) in enumerate(top3):
                            if i < len(payload2.get("top_themes", [])):
                                t = payload2["top_themes"][i]
                                t["label"]        = label
                                t["review_count"] = len(reviews)
                                t["avg_rating"]   = round(sum(r.rating for r in reviews) / len(reviews), 2) if reviews else 0.0
                                t["pct_of_total"] = round(len(reviews) / total * 100, 1) if total else 0.0
                        try:
                            pulse = PulseNote.model_validate(payload2)
                            word_count = _count_pulse_words(pulse)
                            logger.info("Word-count corrective succeeded — now %d words", word_count)
                        except ValidationError:
                            logger.warning("Word-count corrective response failed validation — using original")
                # Use whatever pulse we have (original or corrected) — log final count
                logger.info(
                    "PulseNote built — %d themes | %d total reviews | avg %.2f★ | %d words",
                    len(pulse.top_themes), pulse.total_reviews_analysed, pulse.avg_rating, _count_pulse_words(pulse),
                )
            else:
                logger.info(
                    "PulseNote built — %d themes | %d total reviews | avg %.2f★ | %d words",
                    len(pulse.top_themes), pulse.total_reviews_analysed, pulse.avg_rating, word_count,
                )
            return pulse

        except ValidationError as ve:
            logger.warning("Attempt %d — Pydantic validation failed: %s", attempt + 1, ve)
        except Exception as exc:
            logger.warning("Attempt %d — LLM call failed: %s", attempt + 1, exc)

    logger.error("Pulse building failed after 2 attempts — using rule-based fallback")
    return _rule_based_fallback(top3, week_label, total, avg_rating)
