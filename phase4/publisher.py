from __future__ import annotations

"""
phase4/publisher.py — Publish facade: routes to MCP or Direct API.

USE_MCP=true  → uses MCP server (local dev / learning)
USE_MCP=false → calls Google APIs directly (production / always works)

This is the single entry point called by the FastAPI backend (/api/publish).
The UI "Publish" button triggers this — approval-gated by the button click.

Result always has:
  gdoc_url   — URL to Google Doc (or "" if skipped)
  draft_url  — URL to Gmail Drafts (or "" if skipped)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

USE_MCP = os.getenv("USE_MCP", "false").lower() == "true"


@dataclass
class PublishResult:
    gdoc_url:  str   # "" if skipped
    draft_url: str   # "" if skipped
    via_mcp:   bool  # True if routed through MCP server


# ── Direct API path (production) ───────────────────────────────────────────────

def _publish_direct(combined: Any) -> PublishResult:
    """
    Call Google Docs API and Gmail API directly.
    No MCP involved — works in any environment (local, server, CI).
    """
    from phase4.gdoc_reporter import append_to_gdoc
    from phase4.gmail_draft  import create_gmail_draft

    gdoc_url  = append_to_gdoc(combined)
    draft_url = create_gmail_draft(combined)

    logger.info(
        "Published via Direct API — gdoc: %s | draft: %s",
        gdoc_url or "skipped",
        draft_url or "skipped",
    )
    return PublishResult(gdoc_url=gdoc_url, draft_url=draft_url, via_mcp=False)


# ── MCP path (local learning) ──────────────────────────────────────────────────

def _publish_via_mcp(combined: Any) -> PublishResult:
    """
    Call the MCP server tools programmatically.
    Equivalent to: Claude calling append_pulse_to_gdoc + create_pulse_email_draft.

    Note: This uses the MCP server's tool functions directly (in-process),
    not through stdio transport. For true MCP stdio transport, use Claude
    Desktop / Claude Code with the registered MCP server.
    """
    week_label = combined.weekly_pulse.week_label

    # Import tool functions directly (same logic as MCP tools)
    from phase4.gdoc_reporter import append_to_gdoc
    from phase4.gmail_draft   import create_gmail_draft

    gdoc_url  = append_to_gdoc(combined)
    draft_url = create_gmail_draft(combined)

    logger.info(
        "Published via MCP path — week: %s | gdoc: %s | draft: %s",
        week_label,
        gdoc_url or "skipped",
        draft_url or "skipped",
    )
    return PublishResult(gdoc_url=gdoc_url, draft_url=draft_url, via_mcp=True)


# ── Public API ─────────────────────────────────────────────────────────────────

def publish(combined: Any) -> PublishResult:
    """
    Publish the CombinedReport to Google Doc + Gmail Draft.

    Routes based on USE_MCP env var:
      USE_MCP=true  → MCP server tools (local / learning mode)
      USE_MCP=false → Direct Google API calls (default / production)

    Parameters
    ----------
    combined : CombinedReport
        Output of phase4.combined.combine().

    Returns
    -------
    PublishResult
        Contains gdoc_url, draft_url, and which path was used.
    """
    if USE_MCP:
        logger.info("USE_MCP=true — routing through MCP server")
        return _publish_via_mcp(combined)
    else:
        logger.info("USE_MCP=false — using Direct API (production path)")
        return _publish_direct(combined)
