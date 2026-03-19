from __future__ import annotations

"""
phase4/gdoc_reporter.py — Phase 4C: Append CombinedReport to a Google Doc.

Uses a Google Service Account — no browser, no refresh token, no OAuth2 flow.
Uses rich text formatting: bold headers, coloured title, indented content.

Setup (one-time, ~5 minutes):
  1. Go to console.cloud.google.com → New project (or existing)
  2. Enable "Google Docs API"
  3. IAM & Admin → Service Accounts → Create Service Account → Download JSON key
  4. Save the JSON file somewhere safe (e.g. ~/.groww/service_account.json)
  5. Open your Google Doc → Share → paste the service account email → Editor role
  6. Add to .env:
       GDOC_DOC_ID=<Doc ID from URL: /d/<THIS>/edit>
       GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service_account.json

Approval-gated: only called when user clicks "Publish" in the UI.
Idempotent: checks for week-label marker before appending — no duplicates on re-runs.
Skipped silently if GDOC_DOC_ID or GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env.
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCOPES    = ["https://www.googleapis.com/auth/documents"]
_GREEN     = {"red": 0.0, "green": 0.702, "blue": 0.525}   # #00B386 Groww green
_DARK_GREY = {"red": 0.216, "green": 0.255, "blue": 0.318}  # #374151
_MID_GREY  = {"red": 0.420, "green": 0.447, "blue": 0.502}  # #6B7280


# ── Credentials ───────────────────────────────────────────────────────────────

def _get_credentials():
    from google.oauth2.service_account import Credentials
    json_path = os.path.expanduser(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""))
    if not json_path:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON not set in .env")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Service account JSON not found: {json_path}")
    return Credentials.from_service_account_file(json_path, scopes=_SCOPES)


# ── Rich-text request builder ─────────────────────────────────────────────────

class _DocWriter:
    """
    Builds a list of Google Docs API batchUpdate requests.
    Inserts text segments with optional bold, colour, font-size.
    All inserts are at a single anchor index (inserted in reverse order
    so indices remain stable — or built as a block then styled).
    """

    def __init__(self, start_index: int):
        self._idx      = start_index
        self._requests: List[dict] = []
        self._segments: List[tuple] = []   # (text, bold, color, size)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _push(self, text: str, bold=False, color=None, size: int = 11):
        self._segments.append((text, bold, color, size))

    def line(self, text: str, bold=False, color=None, size: int = 11):
        self._push(text + "\n", bold=bold, color=color, size=size)

    def blank(self):
        self._push("\n")

    def indent(self, text: str, bold=False, color=None):
        self._push("    " + text + "\n", bold=bold, color=color)

    # ── finalise into API requests ─────────────────────────────────────────────

    def build(self) -> List[dict]:
        requests = []
        idx = self._idx

        for text, bold, color, size in self._segments:
            requests.append({
                "insertText": {
                    "location": {"index": idx},
                    "text": text,
                }
            })

            style = {}
            fields = []
            if bold:
                style["bold"] = True
                fields.append("bold")
            if color:
                style["foregroundColor"] = {"color": {"rgbColor": color}}
                fields.append("foregroundColor")
            if size != 11:
                style["fontSize"] = {"magnitude": size, "unit": "PT"}
                fields.append("fontSize")

            if fields:
                requests.append({
                    "updateTextStyle": {
                        "range": {
                            "startIndex": idx,
                            "endIndex":   idx + len(text),
                        },
                        "textStyle": style,
                        "fields":    ",".join(fields),
                    }
                })

            idx += len(text)

        return requests


# ── Content builder ───────────────────────────────────────────────────────────

def _strip_emojis(text: str) -> str:
    """Remove emoji characters that break Google Docs API UTF-16 index math."""
    import re
    return re.sub(
        r'[\U00010000-\U0010FFFF'   # supplementary multilingual plane (emojis)
        r'\U0001F300-\U0001F9FF'    # misc symbols & pictographs
        r'\u2600-\u26FF'            # misc symbols
        r'\u2700-\u27BF'            # dingbats
        r']', '', text
    ).strip()


def _build_requests(combined: Any, start_index: int) -> List[dict]:
    """Return batchUpdate requests that insert a richly formatted weekly entry."""
    wp  = combined.weekly_pulse
    w   = _DocWriter(start_index)

    # Separator + title
    w.line("━" * 52, color=_GREEN)
    w.line(f"GROWW Weekly Pulse — {wp.week_label}", bold=True, size=14, color=_GREEN)
    w.line(
        f"Date: {combined.date}  |  Reviews: {wp.total_reviews_analysed}"
        f"  |  Avg ★: {wp.avg_rating:.1f}",
        color=_MID_GREY,
    )
    w.blank()

    # Top Themes
    w.line("TOP THEMES", bold=True, color=_DARK_GREY)
    for i, t in enumerate(wp.themes, 1):
        w.indent(
            f"{i}. {t.label}  —  {t.review_count} reviews · "
            f"{t.avg_rating:.1f}★ · {t.pct_of_total:.0f}%",
            bold=True,
        )
        w.indent(f'   "{t.one_line_summary}"', color=_MID_GREY)
    w.blank()

    # User Quotes
    w.line("WHAT USERS ARE SAYING", bold=True, color=_DARK_GREY)
    for i, q in enumerate(wp.quotes, 1):
        w.indent(f'[{i}] "{_strip_emojis(q)}"', color=_MID_GREY)
    w.blank()

    # Action Ideas
    w.line("ACTION IDEAS", bold=True, color=_DARK_GREY)
    for i, idea in enumerate(wp.action_ideas, 1):
        w.indent(f"[{i}] {idea}")
    w.blank()

    # Fee Explanation
    w.line(f"FEE EXPLANATION: {combined.fee_scenario}", bold=True, color=_DARK_GREY)
    for b in combined.explanation_bullets:
        w.indent(f"• {b}")
    w.blank()
    w.line("Sources:", bold=True, color=_MID_GREY)
    for link in combined.source_links:
        w.indent(link, color=_GREEN)
    w.line(f"Last checked: {combined.last_checked}", color=_MID_GREY)

    # Closing separator
    w.line("━" * 52, color=_GREEN)
    w.blank()

    return w.build()


# ── Doc helpers ───────────────────────────────────────────────────────────────

def _already_in_doc(doc: Dict, week_label: str) -> bool:
    """Return True if this week's entry is already in the doc (idempotency)."""
    for element in doc.get("body", {}).get("content", []):
        for pe in element.get("paragraph", {}).get("elements", []):
            if f"Weekly Pulse — {week_label}" in pe.get("textRun", {}).get("content", ""):
                return True
    return False


def _get_end_index(doc: Dict) -> int:
    """Return the insertion index at the end of the document body."""
    content = doc.get("body", {}).get("content", [])
    if not content:
        return 1
    end = content[-1].get("endIndex", 1)
    return max(1, end - 1)


def _delete_week_section(service, doc_id: str, doc: Dict, week_label: str):
    """Delete the existing week section from the doc so it can be replaced."""
    content = doc.get("body", {}).get("content", [])
    start_idx = None
    end_idx   = None
    marker    = f"Weekly Pulse — {week_label}"
    sep       = "━" * 52

    for i, element in enumerate(content):
        for pe in element.get("paragraph", {}).get("elements", []):
            text = pe.get("textRun", {}).get("content", "")
            if marker in text and start_idx is None:
                # Find the separator line just before this
                for j in range(max(0, i - 2), i + 1):
                    for pej in content[j].get("paragraph", {}).get("elements", []):
                        if sep in pej.get("textRun", {}).get("content", ""):
                            start_idx = content[j].get("startIndex", element.get("startIndex"))
                            break
                    if start_idx is not None:
                        break
                if start_idx is None:
                    start_idx = element.get("startIndex", 1)

    if start_idx is None:
        return

    # Find closing separator after the marker (include trailing blank line)
    found_marker = False
    closing_sep_idx = None  # index in content list of closing separator
    for ci, element in enumerate(content):
        for pe in element.get("paragraph", {}).get("elements", []):
            text = pe.get("textRun", {}).get("content", "")
            if marker in text:
                found_marker = True
            if found_marker and sep in text and element.get("startIndex", 0) > start_idx:
                end_idx = element.get("endIndex", element.get("startIndex", 0) + len(text))
                closing_sep_idx = ci
                break
        if end_idx is not None:
            break

    # Include trailing blank line — but never delete the document's final newline
    doc_end = _get_end_index(doc) + 1  # actual last endIndex in the doc
    if closing_sep_idx is not None and closing_sep_idx + 1 < len(content):
        next_el = content[closing_sep_idx + 1]
        next_text = "".join(
            pe.get("textRun", {}).get("content", "")
            for pe in next_el.get("paragraph", {}).get("elements", [])
        )
        candidate = next_el.get("endIndex", end_idx)
        if next_text.strip() == "" and candidate < doc_end:
            end_idx = candidate

    if end_idx is None or start_idx >= end_idx:
        return

    try:
        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"deleteContentRange": {"range": {
                "startIndex": start_idx,
                "endIndex":   end_idx,
            }}}]},
        ).execute()
        logger.info("Deleted existing section for week %s (idx %d→%d)", week_label, start_idx, end_idx)
    except Exception as exc:
        logger.warning("Could not delete existing section (will append fresh): %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def append_to_gdoc(combined: Any, doc_id: Optional[str] = None) -> str:
    """
    Append the CombinedReport as a richly formatted section to the Google Doc.

    Returns URL of the updated Google Doc, or "" if skipped.
    - Skipped silently if GDOC_DOC_ID or GOOGLE_SERVICE_ACCOUNT_JSON not set.
    - Idempotent: skips if this week already appears in the doc.
    """
    doc_id = doc_id or os.getenv("GDOC_DOC_ID", "")
    if not doc_id:
        logger.info("GDOC_DOC_ID not set — skipping Google Doc append")
        return ""

    json_path = os.path.expanduser(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""))
    if not json_path:
        logger.info("GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping Google Doc append")
        return ""

    from googleapiclient.discovery import build

    creds   = _get_credentials()
    service = build("docs", "v1", credentials=creds, cache_discovery=False)

    doc        = service.documents().get(documentId=doc_id).execute()
    week_label = combined.weekly_pulse.week_label
    doc_url    = f"https://docs.google.com/document/d/{doc_id}/edit"

    if _already_in_doc(doc, week_label):
        logger.info("Week %s already in Google Doc — replacing. %s", week_label, doc_url)
        _delete_week_section(service, doc_id, doc, week_label)
        doc = service.documents().get(documentId=doc_id).execute()

    end_index = _get_end_index(doc)
    requests  = _build_requests(combined, end_index)

    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()

    logger.info("Appended week %s to Google Doc: %s", week_label, doc_url)
    return doc_url
