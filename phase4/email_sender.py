from __future__ import annotations

"""
phase4/email_sender.py — Canonical Gmail SMTP dispatch implementation.
reporter/email_sender.py delegates to this module.

Sends the weekly pulse as MIMEMultipart('alternative'):
  - text/plain  fallback (for clients that don't render HTML)
  - text/html   primary  (Jinja2-rendered email)

Port 465 → smtplib.SMTP_SSL (implicit TLS)
Port 587 → smtplib.SMTP  + starttls()
Non-fatal: logs on failure instead of raising — the report is already saved to disk.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from analyser.pulse_builder import PulseNote
from config.settings import Settings

logger = logging.getLogger(__name__)


def send_pulse_email(
    pulse: PulseNote,
    text_body: str,
    html_body: str,
    config: Settings,
) -> bool:
    """
    Send the weekly pulse note via Gmail SMTP.

    Returns True on success, False on any failure (non-fatal).
    Logs errors rather than raising — the report is already saved to disk.
    """
    if not config.email_to:
        logger.warning("EMAIL_TO is empty — skipping email dispatch")
        return False

    if not config.smtp_user or not config.smtp_password:
        logger.warning("SMTP credentials not configured — skipping email dispatch")
        return False

    subject = (
        f"GROWW Weekly Pulse | {pulse.week_label} | "
        f"{pulse.total_reviews_analysed} reviews analysed"
    )
    sender = config.email_from or config.smtp_user
    recipients = config.email_to

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    # plain text first (lower preference), HTML second (higher preference)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if config.smtp_port == 465:
            with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port) as smtp:
                smtp.login(config.smtp_user, config.smtp_password)
                smtp.sendmail(sender, recipients, msg.as_string())
        else:
            # port 587 — STARTTLS
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(config.smtp_user, config.smtp_password)
                smtp.sendmail(sender, recipients, msg.as_string())

        logger.info(
            "Pulse email sent — subject: %r → %s",
            subject,
            ", ".join(recipients),
        )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "SMTP authentication failed — check SMTP_USER / SMTP_PASSWORD in .env. "
            "For Gmail, use a 16-char App Password (Settings → Security → App Passwords)."
        )
    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending pulse email: %s", exc)
    except OSError as exc:
        logger.error("Network error while connecting to %s:%d — %s",
                     config.smtp_host, config.smtp_port, exc)

    return False
