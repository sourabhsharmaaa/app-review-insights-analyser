from __future__ import annotations

"""
phase2/pii_filter.py — PII scrubbing security gate (canonical implementation).
processor/pii_filter.py imports from here.

Two modes controlled by SCRUB_MODE env var:
  "regex"    (default) — fast, no extra deps, handles Indian phone/PAN/Aadhaar/email
  "presidio" — Presidio + spaCy en_core_web_lg for named-entity detection;
               regex is always applied on top for Indian-specific patterns

Layer 1 (structural) : userName never modelled — enforced in scraper/models.py
Layer 2 (structural) : title not stored        — removed from Review model
Layer 3 (content)    : this file — scrubs text field of every Review
"""

import logging
import os
import re
from typing import List

from scraper.models import Review

logger = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────
_PHONE_RE   = re.compile(r'\b[6-9]\d{9}\b')
_PAN_RE     = re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b')
_AADHAAR_RE = re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')
_EMAIL_RE   = re.compile(r'\b[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}\b')

# ── Lazy Presidio engines ──────────────────────────────────────────────────────
_analyzer   = None
_anonymizer = None


def _get_presidio_engines():
    global _analyzer, _anonymizer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
        _analyzer   = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


# ── Scrub helpers ──────────────────────────────────────────────────────────────

def _apply_regex(text: str) -> str:
    """Replace Indian PII patterns with typed tokens."""
    text = _PHONE_RE.sub("<PHONE>", text)
    text = _PAN_RE.sub("<PAN>", text)
    text = _AADHAAR_RE.sub("<ID>", text)
    text = _EMAIL_RE.sub("<EMAIL>", text)
    return text


def _apply_presidio(text: str) -> str:
    """Presidio NER scrub, then regex pass for Indian-specific patterns."""
    try:
        analyzer, anonymizer = _get_presidio_engines()
        results = analyzer.analyze(
            text=text,
            entities=["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "LOCATION"],
            language="en",
        )
        if results:
            text = anonymizer.anonymize(text=text, analyzer_results=results).text
    except Exception as exc:
        logger.warning("Presidio failed (%s) — falling back to regex", exc)
    return _apply_regex(text)


def _scrub_text(text: str) -> str:
    mode = os.getenv("SCRUB_MODE", "regex").lower()
    return _apply_presidio(text) if mode == "presidio" else _apply_regex(text)


# ── Public API ─────────────────────────────────────────────────────────────────

def scrub_review(review: Review) -> Review:
    """
    Scrub PII from a single review's text field.
    Returns a new Review with sanitised text (model_copy — original untouched).
    """
    return review.model_copy(update={"text": _scrub_text(review.text)})


def scrub_batch(reviews: List[Review]) -> List[Review]:
    """
    Scrub PII from all reviews.
    Logs how many reviews had at least one entity removed.
    """
    scrubbed = [scrub_review(r) for r in reviews]
    hits = sum(1 for orig, clean in zip(reviews, scrubbed) if orig.text != clean.text)
    logger.info(
        "PII scrub complete — %d/%d reviews had entities removed (mode=%s)",
        hits, len(reviews), os.getenv("SCRUB_MODE", "regex"),
    )
    return scrubbed
