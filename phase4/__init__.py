# Phase 4 — Reporting & Email
#
# formatter.py              : PulseNote → plain-text one-pager + Jinja2 HTML
# email_sender.py           : Gmail SMTP dispatch (MIMEMultipart, port 465/587)
# fee_scraper.py            : Scrapes exit load details → FeeExplanation (Phase 4A)
# gdoc_reporter.py          : Appends combined JSON to Google Doc via API (Phase 4C)
# templates/pulse_email.html: Jinja2 template with inline CSS (email-client safe)
#
# reporter/formatter.py and reporter/email_sender.py are thin delegation wrappers
# that re-export from this package.
