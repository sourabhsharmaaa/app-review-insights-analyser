#!/usr/bin/env python3
"""
scheduler.py — Auto-run pipeline + publish every Monday.

Usage:
    python scheduler.py               # runs on schedule (every Monday 09:00 IST)
    python scheduler.py --now         # run once immediately (for testing)

Schedule is controlled by .env:
    SCHEDULE_DAY  = monday            (default)
    SCHEDULE_TIME = 09:00             (default, 24h format, IST)

What it does each run:
    1. Run full pipeline (scrape → process → analyse → fee → combine)
    2. Auto-publish (append to Google Doc + send email directly to EMAIL_TO)
    3. Log everything to data/logs/scheduler.log

To stop emails: remove or comment out EMAIL_TO in .env
To stop scheduler: pkill -f "python scheduler.py"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

import os

# ── Logging ───────────────────────────────────────────────────────────────────

_LOG_DIR = _ROOT / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_LOG_DIR / "scheduler.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scheduler")


# ── Job ───────────────────────────────────────────────────────────────────────

def run_and_publish() -> None:
    logger.info("=" * 60)
    logger.info("Scheduled job starting...")

    # 1. Run pipeline
    try:
        from pipeline.runner import run_pipeline
        weeks_back  = int(os.getenv("WEEKS_BACK", "12"))
        max_reviews = int(os.getenv("MAX_REVIEWS", "500"))
        logger.info("Running pipeline — weeks_back=%d max_reviews=%d", weeks_back, max_reviews)
        result = run_pipeline(weeks_back=weeks_back, max_reviews=max_reviews, send_email=False)
    except Exception as exc:
        logger.exception("Pipeline failed — aborting publish: %s", exc)
        return

    # 2. Auto-publish (Google Doc + direct email)
    try:
        from storage.cache import load_combined
        from phase4.publisher import publish

        if hasattr(result, "weekly_pulse"):
            week_label = result.weekly_pulse.week_label
        else:
            week_label = getattr(result, "week_label", None)

        if not week_label:
            logger.error("Could not determine week_label — skipping publish")
            return

        combined   = load_combined(week_label)
        pub_result = publish(combined)
        logger.info("Published — gdoc: %s | email: %s",
                    pub_result.gdoc_url or "skipped",
                    pub_result.draft_url or "skipped")
    except Exception as exc:
        logger.exception("Publish failed (non-fatal): %s", exc)

    logger.info("Scheduled job done.")
    logger.info("=" * 60)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    test_interval = int(os.getenv("SCHEDULE_TEST_INTERVAL_MINUTES", "0"))

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    if test_interval > 0:
        trigger = IntervalTrigger(minutes=test_interval, timezone="Asia/Kolkata")
        label   = f"every {test_interval} minutes (TEST MODE)"
    else:
        day  = os.getenv("SCHEDULE_DAY", "monday")
        time = os.getenv("SCHEDULE_TIME", "09:00")
        hour, minute = time.split(":")
        trigger = CronTrigger(day_of_week=day[:3].lower(), hour=int(hour), minute=int(minute))
        label   = f"every {day.capitalize()} at {time} IST"

    scheduler.add_job(run_and_publish, trigger, id="weekly_pulse", name=f"Weekly Pulse — {label}")

    logger.info("Scheduler started — %s", label)
    logger.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GROWW Weekly Pulse Scheduler")
    parser.add_argument("--now", action="store_true",
                        help="Run pipeline + publish once immediately (for testing)")
    args = parser.parse_args()

    if args.now:
        logger.info("--now flag: running pipeline + publish immediately")
        run_and_publish()
    else:
        start_scheduler()
