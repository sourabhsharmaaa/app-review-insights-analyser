from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from scraper.models import Review, ScrapedBatch

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).parent.parent / "data"
_RAW_DIR = _DATA_ROOT / "raw"
_PROCESSED_DIR = _DATA_ROOT / "processed"
_REPORTS_DIR = _DATA_ROOT / "reports"


def _ensure_dirs() -> None:
    for d in (_RAW_DIR, _PROCESSED_DIR, _REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── Raw (Phase 1) ─────────────────────────────────────────────────────────────

def already_scraped(week_label: str) -> bool:
    return (_RAW_DIR / f"reviews_{week_label}.json").exists()


def save_raw(batch: ScrapedBatch) -> None:
    _ensure_dirs()
    path = _RAW_DIR / f"reviews_{batch.week_label}.json"
    path.write_text(batch.model_dump_json(indent=2))
    logger.debug("Saved raw batch → %s", path)


def load_raw(week_label: str) -> ScrapedBatch:
    path = _RAW_DIR / f"reviews_{week_label}.json"
    if not path.exists():
        raise FileNotFoundError(f"No raw cache for week {week_label}. Run scrape first.")
    return ScrapedBatch.model_validate_json(path.read_text())


# ── Processed / PII-filtered (Phase 2) ───────────────────────────────────────

def already_processed(week_label: str) -> bool:
    return (_PROCESSED_DIR / f"reviews_clean_{week_label}.json").exists()


def save_processed(reviews: List[Review], week_label: str) -> None:
    _ensure_dirs()
    path = _PROCESSED_DIR / f"reviews_clean_{week_label}.json"
    payload = [r.model_dump(mode="json") for r in reviews]
    path.write_text(json.dumps(payload, indent=2, default=str))
    logger.debug("Saved %d clean reviews → %s", len(reviews), path)


def load_processed(week_label: str) -> List[Review]:
    path = _PROCESSED_DIR / f"reviews_clean_{week_label}.json"
    if not path.exists():
        raise FileNotFoundError(f"No processed cache for week {week_label}. Run process first.")
    raw = json.loads(path.read_text())
    return [Review.model_validate(r) for r in raw]


# ── Pulse / Analysed (Phase 3) ────────────────────────────────────────────────

def already_analysed(week_label: str) -> bool:
    return (_REPORTS_DIR / f"pulse_{week_label}.json").exists()


def save_pulse(pulse: object, week_label: str) -> None:
    """Accepts a PulseNote (imported lazily to avoid circular imports)."""
    _ensure_dirs()
    path = _REPORTS_DIR / f"pulse_{week_label}.json"
    path.write_text(pulse.model_dump_json(indent=2))
    logger.debug("Saved pulse note → %s", path)


def load_pulse(week_label: str) -> object:
    """Returns a PulseNote (imported lazily)."""
    from analyser.pulse_builder import PulseNote
    path = _REPORTS_DIR / f"pulse_{week_label}.json"
    if not path.exists():
        raise FileNotFoundError(f"No pulse cache for week {week_label}. Run analyse first.")
    return PulseNote.model_validate_json(path.read_text())


# ── Reported (Phase 4) ────────────────────────────────────────────────────────

def already_reported(week_label: str) -> bool:
    return (_REPORTS_DIR / f".reported_{week_label}").exists()


def mark_reported(week_label: str) -> None:
    _ensure_dirs()
    (_REPORTS_DIR / f".reported_{week_label}").touch()
    logger.debug("Marked week %s as reported", week_label)


# ── Combined Report (Phase 4B) ────────────────────────────────────────────────

def already_combined(week_label: str) -> bool:
    return (_REPORTS_DIR / f"combined_{week_label}.json").exists()


def save_combined(combined: object, week_label: str) -> None:
    """Accepts a CombinedReport (imported lazily to avoid circular imports)."""
    _ensure_dirs()
    path = _REPORTS_DIR / f"combined_{week_label}.json"
    path.write_text(combined.model_dump_json(indent=2))
    logger.debug("Saved combined report → %s", path)


def load_combined(week_label: str) -> object:
    """Returns a CombinedReport (imported lazily)."""
    from phase4.combined import CombinedReport
    path = _REPORTS_DIR / f"combined_{week_label}.json"
    if not path.exists():
        raise FileNotFoundError(f"No combined report for week {week_label}. Run combine first.")
    return CombinedReport.model_validate_json(path.read_text())


# ── History ───────────────────────────────────────────────────────────────────

def list_cached_weeks() -> List[str]:
    """Return sorted list of ISO week labels that have a pulse JSON on disk."""
    _ensure_dirs()
    files = sorted(_REPORTS_DIR.glob("pulse_*.json"))
    return [f.stem.replace("pulse_", "") for f in files]
