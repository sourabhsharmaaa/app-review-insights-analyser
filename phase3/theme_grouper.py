from __future__ import annotations

"""
phase3/theme_grouper.py — LLM Call 2 (canonical implementation).
analyser/theme_grouper.py imports from here.

Classifies every review into one of the themes from Call 1.
Processes reviews in batches of 20 with a 20s wait between batches
to stay under Groq's 6,000 TPM free-tier limit.
~2,000 tokens/batch — 25 batches × 20s ≈ 8 min for 500 reviews.
On Groq 429 (rate limit): waits 30s and retries the same batch.
"""

import json
import logging
import os
import time
from typing import Dict, List

from scraper.models import Review

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20

_SYSTEM_PROMPT = (
    "You are classifying app reviews into predefined themes. "
    "Be deterministic. Always use the exact theme label strings provided."
)


def _build_batch_prompt(batch: List[Review], themes: List[str]) -> str:
    theme_list = json.dumps(themes)
    lines = "\n".join(f'{i}: "{r.text[:200]}"' for i, r in enumerate(batch))
    return (
        f"Themes: {theme_list}\n\n"
        "For each review below, output a JSON object mapping the review index (integer) "
        "to exactly one theme label (exact string match from the list above).\n"
        "Return ONLY the JSON object — no explanation, no markdown.\n"
        'Example: {"0": "Payment Failures", "1": "App Performance"}\n\n'
        f"Reviews:\n{lines}"
    )


def _parse_assignments(raw: str) -> Dict[int, str]:
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        raw = raw.lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        return {int(k): str(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, ValueError):
        return {}


def _closest_theme(label: str, themes: List[str]) -> str:
    """Fuzzy-match an unrecognised label to the nearest theme."""
    label_lower = label.lower()
    for t in themes:
        if t.lower() == label_lower:
            return t
    for t in themes:
        if label_lower in t.lower() or t.lower() in label_lower:
            return t
    return themes[0]


def group_reviews_by_theme(
    reviews: List[Review],
    themes: List[str],
    client,
) -> Dict[str, List[Review]]:
    """
    LLM Call 2: classify all reviews into the provided themes.

    Batch size : 20 reviews
    Wait       : 20s between batches (Groq 6,000 TPM safety)
    On 429     : wait 30s, retry the same batch once
    Returns    : dict mapping each theme label → list of Review objects
    """
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    wait_seconds = int(os.getenv("BATCH_WAIT_SECONDS", "20"))

    grouped: Dict[str, List[Review]] = {t: [] for t in themes}
    batches = [reviews[i:i + _BATCH_SIZE] for i in range(0, len(reviews), _BATCH_SIZE)]

    logger.info(
        "Grouping %d reviews into %d themes — %d batches, %ds wait each (~%d min total)",
        len(reviews), len(themes), len(batches), wait_seconds,
        len(batches) * wait_seconds // 60,
    )

    for idx, batch in enumerate(batches):
        if idx > 0:
            logger.debug("Waiting %ds before batch %d/%d…", wait_seconds, idx + 1, len(batches))
            time.sleep(wait_seconds)

        prompt = _build_batch_prompt(batch, themes)
        success = False

        for attempt in range(2):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature=0.0,
                    max_tokens=512,
                )
                raw = response.choices[0].message.content or ""
                assignments = _parse_assignments(raw)

                for local_idx, review in enumerate(batch):
                    label = assignments.get(local_idx)
                    if label and label in themes:
                        grouped[label].append(review)
                    elif label:
                        matched = _closest_theme(label, themes)
                        logger.debug("Unrecognised label %r → matched to %r", label, matched)
                        grouped[matched].append(review)
                    else:
                        # fallback: assign to most-populated theme
                        fallback = max(grouped, key=lambda t: len(grouped[t]))
                        grouped[fallback].append(review)

                logger.debug("Batch %d/%d done (%d reviews)", idx + 1, len(batches), len(batch))
                success = True
                break

            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str or "rate limit" in err_str:
                    logger.warning("Rate limit hit on batch %d — waiting 30s then retrying", idx + 1)
                    time.sleep(30)
                else:
                    logger.warning("Batch %d attempt %d failed: %s", idx + 1, attempt + 1, exc)

        if not success:
            logger.warning("Batch %d failed after retries — assigning to first theme", idx + 1)
            for review in batch:
                grouped[themes[0]].append(review)

    total = sum(len(v) for v in grouped.values())
    logger.info("Grouping complete — %d reviews assigned across %d themes", total, len(themes))
    for theme, group_reviews in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        logger.info("  %-40s %d reviews", theme, len(group_reviews))

    return grouped
