from __future__ import annotations

# Delegates to phase4/email_sender.py — canonical implementation lives there.
from phase4.email_sender import send_pulse_email  # noqa: F401

__all__ = ["send_pulse_email"]
