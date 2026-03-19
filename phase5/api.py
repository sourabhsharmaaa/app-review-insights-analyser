from __future__ import annotations

"""
phase5/api.py — FastAPI backend for the React UI.

Endpoints:
  GET  /api/weeks                   → list all cached week labels
  GET  /api/pulse/{week_label}      → full PulseNote JSON
  GET  /api/pulse/{week_label}/text → plain-text render
  POST /api/run                     → SSE stream: run pipeline with live progress
"""

import asyncio
import json
import logging
import queue
import sys
import threading
from pathlib import Path
from typing import Generator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# ensure project root is on sys.path when this module is imported directly
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── File logging setup ────────────────────────────────────────────────────────
_LOG_DIR = _ROOT / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "api.log"

_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(_file_handler)
# also keep uvicorn + httpx logs going to the file
for _name in ("uvicorn", "uvicorn.access", "uvicorn.error", "httpx"):
    logging.getLogger(_name).addHandler(_file_handler)

from config.settings import Settings
from reporter.formatter import render_text, render_html
from storage.cache import list_cached_weeks, load_pulse, already_analysed

logger = logging.getLogger(__name__)

app = FastAPI(title="GROWW Pulse API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vercel + localhost
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_settings() -> Settings:
    return Settings.from_env()


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/weeks")
def get_weeks():
    """Return all weeks that have a cached pulse report."""
    weeks = list_cached_weeks()
    result = []
    for w in weeks:
        pulse = load_pulse(w)
        if pulse:
            result.append({
                "week_label": pulse.week_label,
                "total_reviews": pulse.total_reviews_analysed,
                "avg_rating": pulse.avg_rating,
                "top_theme": pulse.top_themes[0].label if pulse.top_themes else "",
                "generated_at": pulse.generated_at.isoformat(),
            })
    return result


@app.get("/api/pulse/{week_label}")
def get_pulse(week_label: str):
    """Return the full PulseNote JSON for the given week."""
    pulse = load_pulse(week_label)
    if not pulse:
        raise HTTPException(status_code=404, detail=f"No pulse found for {week_label}")
    return pulse.model_dump(mode="json")


@app.get("/api/pulse/{week_label}/text")
def get_pulse_text(week_label: str):
    """Return the plain-text render of a pulse."""
    pulse = load_pulse(week_label)
    if not pulse:
        raise HTTPException(status_code=404, detail=f"No pulse found for {week_label}")
    return {"text": render_text(pulse)}


@app.get("/api/run")
def run_pipeline_sse(weeks_back: int = 12, force: bool = False, max_reviews: int = 0):
    """
    Stream pipeline progress via Server-Sent Events.
    Each event has shape: { step, pct, message }
    Final event: { step: "done", pct: 100, pulse: <PulseNote JSON> }
    Error event: { step: "error", message: <str> }
    """
    progress_queue: queue.Queue = queue.Queue()

    def progress_callback(step: str, pct: int) -> None:
        progress_queue.put({"step": step, "pct": pct})

    def _normalise(result) -> dict:
        """
        Normalise CombinedReport or PulseNote into a flat UI-friendly dict.
        PulseNote  → already flat (week_label, top_themes, user_quotes …)
        CombinedReport → nested weekly_pulse; flatten + include fee fields.
        """
        if hasattr(result, "weekly_pulse"):
            wp = result.weekly_pulse
            return {
                "week_label":              wp.week_label,
                "total_reviews_analysed":  wp.total_reviews_analysed,
                "avg_rating":              wp.avg_rating,
                "top_themes":              [t.model_dump() for t in wp.themes],
                "user_quotes":             wp.quotes,
                "action_ideas":            wp.action_ideas,
                "generated_at":            result.date.isoformat(),
                # fee fields shown in UI
                "fee_scenario":            result.fee_scenario,
                "explanation_bullets":     result.explanation_bullets,
                "source_links":            result.source_links,
                "last_checked":            str(result.last_checked),
            }
        # fallback: plain PulseNote
        return result.model_dump(mode="json")

    def run_in_thread():
        try:
            # lazy import to avoid loading heavy deps at startup
            from pipeline.runner import run_pipeline
            kwargs = dict(
                weeks_back=weeks_back,
                send_email=False,
                force=force,
                progress_callback=progress_callback,
            )
            if max_reviews > 0:
                kwargs["max_reviews"] = max_reviews
            result = run_pipeline(**kwargs)
            progress_queue.put({"step": "done", "pct": 100, "pulse": _normalise(result)})
        except Exception as exc:
            logger.exception("Pipeline error")
            progress_queue.put({"step": "error", "message": str(exc)})

    def event_generator() -> Generator[str, None, None]:
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        while True:
            try:
                msg = progress_queue.get(timeout=300)  # 5-min max wait
            except queue.Empty:
                yield _sse("error", {"message": "Pipeline timed out"})
                break
            event = msg.get("step", "progress")
            yield _sse(event, msg)
            if event in ("done", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")



@app.post("/api/publish/{week_label}")
def publish_report(week_label: str):
    """
    Publish the combined report for a given week.

    Two actions (approval-gated by this button click):
      1. Append CombinedReport to Google Doc (via Service Account)
      2. Create Gmail Draft with pulse + fee explanation (via OAuth2)

    Routes via USE_MCP env var:
      USE_MCP=true  → MCP server tools (local learning)
      USE_MCP=false → Direct API calls (production)

    Returns gdoc_url and draft_url (empty string if skipped/not configured).
    """
    from storage.cache import load_combined
    from phase4.publisher import publish

    try:
        combined = load_combined(week_label)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No combined report for {week_label}. Run the pipeline first."
        )

    result = publish(combined)

    return {
        "status":     "published",
        "week_label": week_label,
        "gdoc_url":   result.gdoc_url,
        "draft_url":  result.draft_url,
        "via_mcp":    result.via_mcp,
    }
