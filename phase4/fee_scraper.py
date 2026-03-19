from __future__ import annotations

"""
phase4/fee_scraper.py — Fee Explanation scraper (Phase 4A).

Scrapes exit load details from Groww's public exit-load explainer page,
returns a FeeExplanation with ≤6 plain-language bullets and exactly 2
pinned official source links.

Design decisions:
  - source_links are HARDCODED (not scraped) — 2 official Groww URLs, always present
  - Bullet content is scraped from FEE_FUND_URL; falls back to hardcoded bullets if scrape fails
  - Non-fatal: a scrape failure never breaks the pipeline
  - Neutral, facts-only tone enforced in fallback bullets and scraping criteria
  - No recommendations, no comparisons between funds/platforms
"""

import logging
import os
import re
import datetime as _dt
from typing import List

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

# Always exactly 2 pinned official Groww source links — hardcoded, never scraped
_SOURCE_LINKS: List[str] = [
    "https://groww.in/p/exit-load-in-mutual-funds",
    "https://groww.in/pricing",
]

_DEFAULT_FUND_URL = "https://groww.in/p/exit-load-in-mutual-funds"

# Keywords that indicate exit-load relevant sentences
_EXIT_LOAD_KEYWORDS = [
    "exit load", "exit loads", "redemption", "redeemed", "redeem",
    "holding period", "lock-in", "nav", "deducted", "sip", "instalment",
    "1%", "0.5%", "charge", "fee", "mutual fund",
]

# Max bullets to return (requirement: ≤6)
_MAX_BULLETS = 6
_MIN_BULLETS = 3


# ── Pydantic model ───────────────────────────────────────────────────────────

class FeeExplanation(BaseModel):
    scenario: str                   # e.g. "Mutual Fund Exit Load"
    bullets: List[str]              # 3–6 plain-language facts, neutral tone
    source_links: List[str]         # always exactly 2 official Groww URLs
    last_checked: _dt.date          # date the scrape ran


# ── Hardcoded fallback ────────────────────────────────────────────────────────

def _fallback() -> FeeExplanation:
    """
    Returns a hardcoded FeeExplanation when scraping fails.
    Content is manually verified from Groww's official pages.
    Neutral, facts-only — no recommendations or fund comparisons.
    """
    return FeeExplanation(
        scenario="Mutual Fund Exit Load",
        bullets=[
            "Exit load is a fee charged when you redeem mutual fund units before a specified holding period ends.",
            "Most equity mutual funds on Groww levy 1% exit load if units are redeemed within 12 months of purchase.",
            "Debt funds typically carry 0–0.5% exit load for redemptions within 30–90 days of purchase.",
            "Exit load is deducted from the redemption NAV — the amount credited to your account is reduced accordingly.",
            "Each SIP instalment carries its own exit load clock, starting from its individual purchase date.",
            "Exit load details for each fund are displayed on the fund's page on Groww before you invest.",
        ],
        source_links=_SOURCE_LINKS,
        last_checked=_dt.date.today(),
    )


# ── Scraping helpers ─────────────────────────────────────────────────────────

def _is_relevant(text: str) -> bool:
    """Return True if the text contains exit-load relevant content."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in _EXIT_LOAD_KEYWORDS)


def _clean(text: str) -> str:
    """Normalise whitespace and strip trailing punctuation noise."""
    text = re.sub(r"\s+", " ", text).strip()
    # Remove footnote markers like [1], *, †
    text = re.sub(r"\[\d+\]|\*+|†", "", text).strip()
    return text


def _dedup(bullets: List[str]) -> List[str]:
    """Remove exact duplicates while preserving order."""
    seen: set = set()
    unique: List[str] = []
    for b in bullets:
        if b not in seen:
            seen.add(b)
            unique.append(b)
    return unique


def _extract_bullets(soup: BeautifulSoup) -> List[str]:
    """
    Extract exit-load relevant bullet points from the page HTML.

    Strategy:
    1. Try <li> elements inside article/main/section containers
    2. Fall back to <p> elements with relevant keywords
    3. Filter to sentences containing exit-load keywords
    4. Cap at _MAX_BULLETS, ensure at least _MIN_BULLETS
    """
    bullets: List[str] = []

    # Priority 1: <li> elements in article / main content areas
    for container_tag in ["article", "main", "section", "div"]:
        containers = soup.find_all(container_tag)
        for container in containers:
            for li in container.find_all("li"):
                text = _clean(li.get_text())
                if len(text) > 20 and _is_relevant(text):
                    bullets.append(text)
                if len(bullets) >= _MAX_BULLETS:
                    break
            if len(bullets) >= _MAX_BULLETS:
                break

    bullets = _dedup(bullets)
    if len(bullets) >= _MIN_BULLETS:
        return bullets[:_MAX_BULLETS]

    # Priority 2: <p> elements with relevant content
    for p in soup.find_all("p"):
        text = _clean(p.get_text())
        if len(text) > 30 and _is_relevant(text):
            # Split long paragraphs at sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 20 and _is_relevant(sentence):
                    bullets.append(sentence)
                if len(bullets) >= _MAX_BULLETS:
                    break
        if len(bullets) >= _MAX_BULLETS:
            break

    return _dedup(bullets)[:_MAX_BULLETS]


# ── HTTP fetch with retry ────────────────────────────────────────────────────

@retry(
    wait=wait_exponential(min=2, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    response = httpx.get(url, headers=headers, follow_redirects=True, timeout=15.0)
    response.raise_for_status()
    return response.text


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_fee_explanation(fund_url: str | None = None) -> FeeExplanation:
    """
    Scrape exit load details from fund_url (defaults to FEE_FUND_URL env var,
    then Groww's official exit-load explainer page).

    Returns a FeeExplanation with:
      - scenario : "Mutual Fund Exit Load"
      - bullets  : 3–6 scraped facts (neutral, facts-only, no recommendations)
      - source_links : always exactly 2 pinned Groww official URLs
      - last_checked : today's date

    Never raises — falls back to hardcoded bullets on any scrape failure.
    """
    url = fund_url or os.getenv("FEE_FUND_URL", _DEFAULT_FUND_URL)
    logger.info("Fetching fee explanation from: %s", url)

    try:
        html = _fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        # Remove nav, footer, script, style tags — noise
        for tag in soup(["nav", "footer", "script", "style", "header"]):
            tag.decompose()

        bullets = _extract_bullets(soup)

        if len(bullets) < _MIN_BULLETS:
            logger.warning(
                "Only %d relevant bullets found (need ≥%d) — using fallback",
                len(bullets), _MIN_BULLETS,
            )
            return _fallback()

        logger.info("Fee explanation scraped — %d bullets extracted", len(bullets))
        return FeeExplanation(
            scenario="Mutual Fund Exit Load",
            bullets=bullets[:_MAX_BULLETS],
            source_links=_SOURCE_LINKS,
            last_checked=_dt.date.today(),
        )

    except Exception as exc:
        logger.warning("Fee scrape failed (%s: %s) — using hardcoded fallback", type(exc).__name__, exc)
        return _fallback()
