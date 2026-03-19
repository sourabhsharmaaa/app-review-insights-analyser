from __future__ import annotations

"""
phase3/theme_generator.py — LLM Call 1 (canonical implementation).
analyser/theme_generator.py imports from here.

Samples 50 reviews → asks Groq to identify 3-5 recurring themes → returns list[str].
~4,200 tokens total — safe under Groq 6,000 TPM free tier.
Retries once with a corrective prompt on JSON parse failure.
"""

import json
import logging
import os
import random
from typing import List

from scraper.models import Review

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 50

_SYSTEM_PROMPT = (
    "You are a product analyst for an Indian investment and stock trading app called GROWW. "
    "Your job is to identify recurring pain points and themes from user reviews."
)


def _build_prompt(reviews: List[Review], corrective: bool = False) -> str:
    texts = "\n".join(f"- {r.text[:300]}" for r in reviews)
    prefix = "Your previous response was not valid JSON array. Try again.\n\n" if corrective else ""
    return (
        f"{prefix}Given these {len(reviews)} user reviews, identify 3 to 5 broad recurring themes.\n"
        "Return ONLY a JSON array of theme label strings — no explanation, no markdown.\n"
        "Each label should be 2–5 words, specific to a fintech/investment app.\n"
        'Example: ["Payment Failures", "KYC Friction", "App Performance", "Customer Support"]\n\n'
        f"Reviews:\n{texts}"
    )


def _parse_themes(raw: str) -> List[str] | None:
    """Extract a clean list of strings from LLM output."""
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        raw = raw.lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(t, str) for t in parsed):
            return [t.strip() for t in parsed if t.strip()]
    except json.JSONDecodeError:
        pass
    return None


def generate_themes(reviews: List[Review], client) -> List[str]:
    """
    LLM Call 1: sample up to 50 reviews, return 3–5 theme label strings.

    Model : llama-3.3-70b-versatile
    Temp  : 0.2
    Tokens: 256 max
    ~4,200 tokens total — safe under Groq 6,000 TPM free tier.
    Retries once with corrective prompt on JSON parse failure.
    """
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    sample = random.sample(reviews, min(_SAMPLE_SIZE, len(reviews)))
    logger.info("Generating themes from %d sampled reviews", len(sample))

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": _build_prompt(sample, corrective=(attempt > 0))},
                ],
                temperature=0.2,
                max_tokens=256,
            )
            raw = response.choices[0].message.content or ""
            themes = _parse_themes(raw)

            if themes:
                themes = themes[:5]
                if len(themes) < 3:
                    themes += [f"General Feedback {i+1}" for i in range(3 - len(themes))]
                logger.info("Themes identified: %s", themes)
                return themes

            logger.warning("Attempt %d — could not parse themes from: %r", attempt + 1, raw[:200])

        except Exception as exc:
            logger.warning("Attempt %d — LLM call failed: %s", attempt + 1, exc)
            if attempt == 1:
                break

    logger.error("Theme generation failed after 2 attempts — using generic fallback")
    return ["Payment & Transaction Issues", "App Performance", "Customer Support", "User Experience"]
