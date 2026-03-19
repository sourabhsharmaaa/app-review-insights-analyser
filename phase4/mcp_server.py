from __future__ import annotations

"""
phase4/mcp_server.py — Custom MCP Server for GROWW Weekly Pulse.

Exposes two tools to any MCP-compatible client (Claude Desktop, Claude Code):
  1. append_pulse_to_gdoc   — appends CombinedReport to configured Google Doc
  2. create_pulse_email_draft — creates Gmail draft with pulse + fee explanation

How MCP works here:
  - This script runs as a subprocess alongside Claude
  - Claude calls tools by name with JSON arguments
  - Each tool call is approval-gated (Claude asks you before running)
  - Communicates via stdio (stdin/stdout) — standard MCP transport

Usage (registered in ~/.claude/mcp.json automatically by setup):
  Claude sees these tools and can call them during conversation.

For production: use phase4/publisher.py with USE_MCP=false instead,
which calls gdoc_reporter and gmail_draft directly without MCP overhead.

Requires Python 3.10+ (MCP SDK requirement).
"""

import json
import logging
import os
import sys

# Add project root to path so phase4.* imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before importing any phase modules
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# ── MCP Server ─────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "groww-pulse",
    instructions=(
        "Tools for GROWW Weekly Pulse pipeline. "
        "Use append_pulse_to_gdoc to save the report to Google Docs, "
        "and create_pulse_email_draft to create a Gmail draft for review. "
        "Always ask the user for approval before calling either tool."
    ),
)


# ── Tool 1: Append to Google Doc ───────────────────────────────────────────────

@mcp.tool()
def append_pulse_to_gdoc(week_label: str) -> str:
    """
    Append the weekly pulse combined report to the configured Google Doc.

    Loads the cached CombinedReport for the given week and appends it
    to the Google Doc specified by GDOC_DOC_ID in .env.

    Idempotent — safe to call multiple times; skips if week already in doc.

    Args:
        week_label: ISO week label e.g. "2026-W12"

    Returns:
        URL of the updated Google Doc, or a status message if skipped.
    """
    try:
        from storage.cache import load_combined
        from phase4.gdoc_reporter import append_to_gdoc

        combined = load_combined(week_label)
        if combined is None:
            return f"❌ No combined report found for {week_label}. Run the pipeline first."

        url = append_to_gdoc(combined)
        if url:
            return f"✅ Appended to Google Doc: {url}"
        return "⚠️ Skipped — GDOC_DOC_ID or GOOGLE_SERVICE_ACCOUNT_JSON not configured in .env"

    except Exception as exc:
        logger.error("append_pulse_to_gdoc failed: %s", exc)
        return f"❌ Error: {exc}"


# ── Tool 2: Create Gmail Draft ─────────────────────────────────────────────────

@mcp.tool()
def create_pulse_email_draft(week_label: str) -> str:
    """
    Create a Gmail draft with the weekly pulse + fee explanation.

    Loads the cached CombinedReport for the given week and creates
    a Gmail draft ready for review. Does NOT send — user must open
    Gmail Drafts and click Send manually.

    Args:
        week_label: ISO week label e.g. "2026-W12"

    Returns:
        URL to Gmail Drafts folder, or a status message if skipped.
    """
    try:
        from storage.cache import load_combined
        from phase4.gmail_draft import create_gmail_draft

        combined = load_combined(week_label)
        if combined is None:
            return f"❌ No combined report found for {week_label}. Run the pipeline first."

        url = create_gmail_draft(combined)
        if url:
            return f"✅ Gmail draft created — open Drafts to review and send: {url}"
        return "⚠️ Skipped — GMAIL_CLIENT_SECRET not configured in .env"

    except Exception as exc:
        logger.error("create_pulse_email_draft failed: %s", exc)
        return f"❌ Error: {exc}"


# ── Tool 3: Pipeline status ────────────────────────────────────────────────────

@mcp.tool()
def get_pipeline_status() -> str:
    """
    Check which weeks have been processed by the pipeline.

    Returns a summary of all cached weeks with their status
    (raw scraped, processed, analysed, reported).
    """
    try:
        from storage.cache import list_cached_weeks
        weeks = list_cached_weeks()
        if not weeks:
            return "No weeks cached yet. Run the pipeline first."
        return "Cached weeks:\n" + "\n".join(f"  • {w}" for w in sorted(weeks))
    except Exception as exc:
        return f"❌ Error checking status: {exc}"


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
