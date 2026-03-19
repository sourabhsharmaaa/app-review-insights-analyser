from __future__ import annotations

"""
phase0/runner.py — Shared orchestration layer (canonical implementation).
pipeline/runner.py imports from here.

Both the CLI (main.py) and the Web UI (ui/app.py) call run_pipeline().
This is the single source of truth for phase order, idempotency skips,
progress reporting, and error handling.
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from phase0.settings import Settings

logger = logging.getLogger(__name__)

# Streamlit wires this to st.progress(); CLI passes None.
ProgressCallback = Optional[Callable[[str, int], None]]


def _notify(callback: ProgressCallback, label: str, pct: int) -> None:
    """Fire the progress callback if one was provided."""
    if callback is not None:
        callback(label, pct)


def _current_week_label() -> str:
    """
    Return the current ISO week label, e.g. '2026-W12'.
    Always computed from datetime.now(UTC) — never hardcoded.
    """
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def run_pipeline(
    weeks_back: int = 10,
    send_email: bool = False,
    force: bool = False,
    append_gdoc: bool = False,
    progress_callback: ProgressCallback = None,
    max_reviews: int = 0,
):
    """
    Orchestrate all pipeline phases end-to-end.

    Parameters
    ----------
    weeks_back : int
        How many weeks back from today to include reviews.
        Cutoff = datetime.now(UTC) - timedelta(weeks=weeks_back).
    send_email : bool
        If True, dispatch the pulse note email after generating it.
    force : bool
        If True, ignore all caches and re-run every phase from scratch.
    progress_callback : callable, optional
        Called as callback(label: str, pct: int) after each phase.
        Streamlit uses this to update a live progress bar.
        Pass None (default) for CLI usage.

    Returns
    -------
    PulseNote
        The generated (or cached) pulse note for the current week.
    """
    # Lazy imports keep startup fast and avoid circular-import issues.
    from phase1.play_store import fetch_reviews
    from phase2.pii_filter import scrub_batch
    from phase2.deduplicator import deduplicate
    from phase3.theme_generator import generate_themes
    from phase3.theme_grouper import group_reviews_by_theme
    from phase3.pulse_builder import build_pulse, PulseNote
    from phase4.formatter import render_text, render_html
    from phase4.email_sender import send_pulse_email
    from phase4.fee_scraper import fetch_fee_explanation
    from phase4.combined import combine
    from phase4.gdoc_reporter import append_to_gdoc
    from storage.cache import (
        already_scraped, save_raw, load_raw,
        already_processed, save_processed, load_processed,
        already_analysed, save_pulse, load_pulse,
        already_combined, save_combined, load_combined,
        already_reported, mark_reported,
    )
    from scraper.models import ScrapedBatch

    settings = Settings.from_env()
    settings.configure_logging()

    # Override max_reviews if passed explicitly (e.g. from UI slider)
    effective_max = max_reviews if max_reviews > 0 else settings.max_reviews

    week = _current_week_label()
    logger.info("=" * 60)
    logger.info("GROWW Weekly Pulse — pipeline starting")
    logger.info("Week: %s | weeks_back: %d | max_reviews: %d | force: %s",
                week, weeks_back, effective_max, force)
    logger.info("=" * 60)

    # ── Phase 1: Scrape ───────────────────────────────────────────────────────
    if not force and already_scraped(week):
        logger.info("[1/4] SCRAPE — cache hit for %s, skipping", week)
        _notify(progress_callback, "Loaded reviews from cache", 15)
    else:
        logger.info("[1/4] SCRAPE — fetching reviews from Play Store…")
        _notify(progress_callback, "Scraping Play Store reviews…", 5)

        reviews_raw = fetch_reviews(
            app_id=settings.app_id,
            weeks_back=weeks_back,
            max_reviews=effective_max,
        )

        if not reviews_raw:
            raise ScraperError(
                f"Play Store returned 0 reviews for {settings.app_id}. "
                "Check network connectivity or try again later."
            )

        batch = ScrapedBatch(
            app_id=settings.app_id,
            week_label=week,
            scraped_at=datetime.now(timezone.utc),
            reviews=reviews_raw,
        )
        save_raw(batch)
        logger.info("[1/4] SCRAPE — fetched and cached %d reviews", len(reviews_raw))
        _notify(progress_callback, f"Scraped {len(reviews_raw)} reviews", 15)

    # ── Phase 2: PII Filter ───────────────────────────────────────────────────
    if not force and already_processed(week):
        logger.info("[2/4] PROCESS — cache hit for %s, skipping", week)
        clean_reviews = load_processed(week)
        _notify(progress_callback, "Loaded PII-filtered reviews from cache", 30)
    else:
        logger.info("[2/4] PROCESS — running PII scrub + dedup…")
        _notify(progress_callback, "Filtering PII from review text…", 20)

        raw_batch = load_raw(week)
        scrubbed = scrub_batch(raw_batch.reviews)
        clean_reviews = deduplicate(scrubbed)

        save_processed(clean_reviews, week)
        logger.info("[2/4] PROCESS — %d clean reviews after PII scrub + dedup",
                    len(clean_reviews))
        _notify(progress_callback, f"PII filtered — {len(clean_reviews)} clean reviews", 30)

    # ── Phase 3: LLM Analysis ─────────────────────────────────────────────────
    if not force and already_analysed(week):
        logger.info("[3/4] ANALYSE — cache hit for %s, skipping", week)
        pulse = load_pulse(week)
        _notify(progress_callback, "Loaded pulse note from cache", 88)
    else:
        try:
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key)

            logger.info("[3/4] ANALYSE — generating theme labels…")
            _notify(progress_callback, "Generating theme labels with Groq…", 45)
            themes = generate_themes(clean_reviews, client)
            logger.info("[3/4] ANALYSE — themes: %s", themes)

            logger.info("[3/4] ANALYSE — grouping %d reviews by theme…", len(clean_reviews))
            _notify(progress_callback, f"Grouping {len(clean_reviews)} reviews by theme…", 60)
            themed = group_reviews_by_theme(clean_reviews, themes, client)

            logger.info("[3/4] ANALYSE — building pulse note…")
            _notify(progress_callback, "Building weekly pulse note…", 78)
            pulse = build_pulse(themed, week, client)

            save_pulse(pulse, week)
            logger.info("[3/4] ANALYSE — pulse built: %d themes, %d total reviews",
                        len(pulse.top_themes), pulse.total_reviews_analysed)
            _notify(progress_callback, "Pulse note generated ✅", 88)

        except Exception as exc:
            logger.error("[3/4] ANALYSE — failed: %s", exc, exc_info=True)
            raise AnalysisError(f"LLM analysis failed: {exc}") from exc

    # ── Phase 4A: Fee Explanation ─────────────────────────────────────────────
    logger.info("[4/6] FEE — fetching exit load explanation…")
    _notify(progress_callback, "Fetching fee explanation…", 90)
    fee = fetch_fee_explanation()
    logger.info("[4/6] FEE — %d bullets fetched (last_checked: %s)", len(fee.bullets), fee.last_checked)

    # ── Phase 4B: Combine ─────────────────────────────────────────────────────
    if not force and already_combined(week):
        logger.info("[5/6] COMBINE — cache hit for %s, skipping", week)
        combined = load_combined(week)
        _notify(progress_callback, "Loaded combined report from cache", 93)
    else:
        logger.info("[5/6] COMBINE — merging pulse + fee into combined report…")
        _notify(progress_callback, "Building combined report…", 93)
        combined = combine(pulse, fee)
        save_combined(combined, week)
        logger.info("[5/6] COMBINE — saved combined_%s.json", week)

    # ── Phase 4C: Google Doc Append (approval-gated) ─────────────────────────
    if append_gdoc:
        logger.info("[5b/6] GDOC — appending combined report to Google Doc…")
        _notify(progress_callback, "Appending to Google Doc…", 94)
        try:
            doc_url = append_to_gdoc(combined, doc_id=settings.gdoc_doc_id or None)
            if doc_url:
                logger.info("[5b/6] GDOC — appended: %s", doc_url)
                _notify(progress_callback, f"Appended to Google Doc ✅", 94)
        except Exception as exc:
            logger.warning("[5b/6] GDOC — append failed (non-fatal): %s", exc)

    # ── Phase 6: Report ───────────────────────────────────────────────────────
    logger.info("[6/6] REPORT — rendering report…")
    _notify(progress_callback, "Rendering report…", 95)

    text_body = render_text(pulse)
    html_body = render_html(pulse)

    if send_email:
        logger.info("[6/6] REPORT — sending email to: %s", settings.email_to)
        _notify(progress_callback, "Sending email…", 97)
        send_pulse_email(pulse, text_body, html_body, settings)
        mark_reported(week)
        logger.info("[6/6] REPORT — email sent")

    _notify(progress_callback, "Done ✅", 100)
    logger.info("Pipeline complete for week %s", week)
    logger.info("=" * 60)

    return combined


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ScraperError(RuntimeError):
    """Raised when the Play Store scraper returns no usable results."""


class AnalysisError(RuntimeError):
    """Raised when LLM analysis fails after all retries are exhausted."""
