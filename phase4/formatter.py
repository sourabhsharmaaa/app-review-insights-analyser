from __future__ import annotations

"""
phase4/formatter.py — Canonical implementation of PulseNote rendering.
reporter/formatter.py delegates to this module.

render_text()  → plain-text one-pager (email fallback + .txt file)
render_html()  → Jinja2 HTML email body (inline CSS, table-based layout)
"""

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from analyser.pulse_builder import PulseNote

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "pulse_email.html"


def render_text(pulse: PulseNote) -> str:
    """
    Render a PulseNote as a plain-text one-page note.

    Matches the one-page structure from ARCHITECTURE.md:
      - Header bar with week label, review count, avg rating
      - TOP THEMES section
      - WHAT USERS ARE SAYING section
      - ACTION IDEAS section
      - Footer with generated timestamp
    """
    sep = "━" * 52
    thin = "─" * 52

    lines = [
        sep,
        f"  GROWW Weekly Pulse | {pulse.week_label}",
        f"  {pulse.total_reviews_analysed} reviews analysed | Avg rating: {pulse.avg_rating:.1f} ★",
        sep,
        "",
        "TOP THEMES",
        thin,
    ]

    for i, theme in enumerate(pulse.top_themes, 1):
        lines.append(
            f"{i}. {theme.label:<38} {theme.review_count} reviews  "
            f"{theme.avg_rating:.1f}★  ({theme.pct_of_total:.0f}%)"
        )
        lines.append(f'   "{theme.one_line_summary}"')
        lines.append("")

    lines += [
        "WHAT USERS ARE SAYING",
        thin,
    ]
    for quote in pulse.user_quotes:
        lines.append(f'\u275d "{quote}" \u275e')
    lines.append("")

    lines += [
        "ACTION IDEAS",
        thin,
    ]
    for i, idea in enumerate(pulse.action_ideas, 1):
        lines.append(f"{i}. {idea}")
    lines.append("")

    ts = pulse.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    lines += [sep, f"Generated: {ts}", ""]

    return "\n".join(lines)


def render_html(pulse: PulseNote) -> str:
    """
    Render a PulseNote as an HTML email body using the Jinja2 template.
    Uses inline CSS only — no external stylesheets (email client compatibility).
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(_TEMPLATE_NAME)
    ts = pulse.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return template.render(pulse=pulse, generated_at=ts)
