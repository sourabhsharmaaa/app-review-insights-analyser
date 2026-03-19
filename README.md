# GROWW Weekly Pulse — App Review Insights Analyser

An automated pipeline that scrapes Google Play Store reviews for the GROWW investment app, groups them into themes using an LLM, generates a one-page weekly pulse note enriched with a fee explanation, and publishes it to Google Docs + Gmail Draft — with zero PII in any output.

## What is this project?

This is an **AI-powered internal product health dashboard** built for product, support, and leadership teams at GROWW. Instead of manually reading hundreds of Play Store reviews every week, this system automatically surfaces the top user concerns, maps them to themes, explains fee-related queries, and delivers a clean weekly report — ready to read in under 2 minutes.

## Why we made this?

Play Store reviews are a goldmine of raw user feedback, but:
- There are too many to read manually every week
- They contain PII (names, contact info) that must be stripped before any analysis
- Leadership needs a single-page summary, not raw data

We built this to:
1. **Automate insight extraction** — scrape, filter, group, and summarise reviews using LLM
2. **Ensure PII safety** — two-layer PII architecture ensures no user identity leaks downstream
3. **Add fee context** — automatically explain fee-related complaints (exit load) with official sources
4. **Gate publishing** — human approval required before anything reaches Google Docs or Gmail

## How it works & What we used

The pipeline runs in 6 phases, each with a clear single responsibility.

### 1. Scrape (Phase 1)
- Fetches recent Play Store reviews using `google-play-scraper`
- Filters by a rolling date window (`WEEKS_BACK` relative to today)
- Drops `userName` structurally — it never enters any model or file

### 2. Process (Phase 2)
- **PII scrub**: `presidio-analyzer` + `spacy` strips named entities from review text
- **Dedup**: SHA256-based deduplication across overlapping week windows

### 3. Analyse (Phase 3) — 3 LLM calls via Groq
- **Call 1**: Generate 3–5 theme labels from sampled reviews
- **Call 2**: Classify each review into a theme (batched, rate-limit safe)
- **Call 3**: Build a structured `PulseNote` JSON (themes, quotes, action ideas, avg rating)

### 4. Fee Explainer (Phase 4A)
- Scrapes Groww's official exit load page → ≤6 neutral, facts-only bullet points
- Always includes exactly 2 official source links
- Adds `Last checked: <date>` — never recommends or compares

### 5. Combine + Publish (Phase 4B–4D)
- Merges `PulseNote` + `FeeExplanation` into a `CombinedReport` JSON
- **Approval-gated**: user clicks **Publish** in UI to trigger:
  - Append to Google Doc (via Service Account — rich text, coloured headers)
  - Send email directly to `EMAIL_TO` (via Gmail API OAuth2)

### 6. React UI (Phase 5)
- **New Pulse page**: configure weeks, max reviews, run pipeline with live SSE progress
- **History page**: browse all cached weekly reports
- **Publish button**: the single human-approval gate for Doc + Draft

## Demo

> Run locally — see Setup Instructions below.
> Open `http://localhost:5173` after starting frontend + backend.

## Key Features

- **3-call LLM pipeline**: theme generation → classification → pulse writing — each call small and retryable
- **Two-layer PII safety**: structural (userName never modelled) + content (Presidio scrub before any write)
- **Fee Explainer**: live-scraped exit load explanation with hardcoded fallback, 2 official sources, neutral tone
- **MCP integration**: custom MCP server (`phase4/mcp_server.py`) exposes 3 tools for local learning/demo
- **Approval-gated publishing**: Publish button = human gate; Google Doc appended + Gmail Draft created — no auto-send
- **Replace-on-duplicate**: re-publishing a week replaces the existing Doc section cleanly
- **Adaptive UI**: shows "View Google Doc" if configured, falls back to "Download .txt"
- **Real-time progress**: SSE stream drives live progress bar in UI during pipeline run
- **JSON cache**: every phase result cached by ISO week label — re-runs are instant

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| LLM | Groq API (`llama-3.3-70b-versatile`) |
| Review Source | `google-play-scraper` |
| PII Filtering | `presidio-analyzer` + `presidio-anonymizer` + `spacy en_core_web_sm` |
| Fee Scraping | `httpx` + `beautifulsoup4` |
| Google Docs | `google-api-python-client` (Service Account) |
| Gmail | `google-api-python-client` (OAuth2) |
| MCP Server | `fastmcp` |
| Frontend | React + Vite (SSE, real-time progress) |
| Backend | FastAPI (SSE `/api/run`, `/api/publish`) |
| Email Template | Jinja2 |
| Data Validation | Pydantic v2 |
| Resilience | `tenacity` (retry + exponential backoff) |
| Config | `python-dotenv` |
| Testing | `pytest` + `pytest-mock` |

## Project Structure

```
app-review-insights-analyser/
│
├── .env                          # Secrets (gitignored)
├── .env.example                  # Template with all required vars
├── requirements.txt
├── ARCHITECTURE.md
├── README.md
│
├── phase0/                       # Canonical settings + runner
│   ├── settings.py               # Single source of truth for all config
│   └── runner.py                 # Shared pipeline orchestration (CLI + UI)
│
├── phase1/                       # Scraping
│   └── play_store.py             # Fetch, filter, structurally drop userName
│
├── phase2/                       # PII + dedup
│   ├── pii_filter.py             # Presidio scrub — security gate
│   └── deduplicator.py           # SHA256 dedup across weeks
│
├── phase3/                       # LLM analysis
│   ├── theme_generator.py        # LLM Call 1 — 3–5 theme labels
│   ├── theme_grouper.py          # LLM Call 2 — classify reviews (batched)
│   └── pulse_builder.py          # LLM Call 3 — PulseNote JSON
│
├── phase4/                       # Fee explainer + publishing
│   ├── fee_scraper.py            # Scrape exit load → ≤6 bullets + 2 source links
│   ├── combined.py               # Merge PulseNote + FeeExplanation → CombinedReport
│   ├── gdoc_reporter.py          # Append to Google Doc (rich text, replace-on-duplicate)
│   ├── gmail_draft.py            # Send email via Gmail API (OAuth2)
│   ├── publisher.py              # Facade: routes to MCP or Direct API (USE_MCP toggle)
│   ├── mcp_server.py             # Custom MCP server (3 tools — local learning)
│   └── templates/
│       └── pulse_email.html      # Jinja2 HTML email template (fee section inline)
│
├── phase5/                       # FastAPI backend
│   └── api.py                    # SSE /api/run, /api/publish, /api/weeks, /api/pulse
│
├── storage/
│   └── cache.py                  # JSON file cache keyed by ISO week label
│
├── ui/                           # React frontend
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── GeneratePulse.jsx # Pipeline controls + live progress + Publish button
│   │   │   └── History.jsx       # Browse all cached weekly reports
│   │   └── components/
│   │       └── PulsePreview.jsx  # Render PulseNote inline
│   └── .env.local                # VITE_GDOC_DOC_ID for adaptive button
│
└── data/
    ├── raw/                      # reviews_YYYY-WW.json (scraped)
    ├── processed/                # PII-scrubbed reviews
    ├── reports/                  # pulse_YYYY-WW.json, combined_YYYY-WW.json, .txt, .html
    └── logs/                     # api.log
```

## Setup Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- Groq API Key — [console.groq.com](https://console.groq.com)
- Google Cloud project with Docs API + Gmail API enabled

### 1. Clone & create virtual environment
```bash
git clone <repo-url>
cd app-review-insights-analyser
python3.11 -m venv .venv311
source .venv311/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 3. Environment variables
```bash
cp .env.example .env
# Fill in:
# GROQ_API_KEY, GDOC_DOC_ID, GOOGLE_SERVICE_ACCOUNT_JSON,
# GMAIL_CLIENT_SECRET, GMAIL_TOKEN_PATH, EMAIL_TO
```

### 4. One-time Gmail OAuth (creates token for sending email)
```bash
python -c "from phase4.gmail_draft import _get_gmail_credentials; _get_gmail_credentials()"
# Browser opens → approve → token saved to GMAIL_TOKEN_PATH
```

### 5. Start backend
```bash
.venv311/bin/uvicorn phase5.api:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Start frontend
```bash
cd ui
npm install
npm run dev
# Opens http://localhost:5173
```

## How to Re-run

1. Open `http://localhost:5173`
2. Go to **New Pulse** tab
3. Set **Weeks Back** (how far to look) and **Max Reviews** (how many to analyse)
4. Click **Generate Pulse** — live progress streams in real time
5. Review the pulse output on screen
6. Click **Publish** to append to Google Doc + send email to `EMAIL_TO`

## Where MCP Approval Happens

The **Publish button** in the UI is the human approval gate. Nothing is written to Google Docs or Gmail until this button is clicked.

Under the hood, `phase4/publisher.py` routes to:
- `USE_MCP=true` → MCP server tools (`append_pulse_to_gdoc`, `create_pulse_email_draft`) — local learning/demo
- `USE_MCP=false` → Direct Google API calls — production default

The MCP server (`phase4/mcp_server.py`) exposes 3 tools:

| Tool | What it does |
|---|---|
| `append_pulse_to_gdoc` | Appends CombinedReport to Google Doc |
| `create_pulse_email_draft` | Sends email with pulse + fee section via Gmail API |
| `get_pipeline_status` | Returns list of cached weeks |

## Fee Scenario Covered

**Mutual Fund Exit Load**

Exit load is a charge levied when a mutual fund investor redeems units before a specified holding period ends. This is one of the most common fee-related complaints in GROWW Play Store reviews.

The system:
- Scrapes [groww.in/p/exit-load-in-mutual-funds](https://groww.in/p/exit-load-in-mutual-funds) for live facts
- Returns ≤6 plain-language bullets (neutral, facts-only — no advice, no comparisons)
- Always includes exactly 2 official source links
- Adds `Last checked: <date>` for transparency
- Falls back to hardcoded verified bullets if scrape fails

### Source List

| # | URL | Purpose |
|---|---|---|
| 1 | https://groww.in/p/exit-load-in-mutual-funds | Primary fee explanation page |
| 2 | https://groww.in/pricing | Official Groww pricing/charges page |
| 3 | https://console.groq.com | LLM API (Groq — llama-3.3-70b-versatile) |
| 4 | https://console.cloud.google.com | Google Cloud — Docs API + Gmail API setup |
| 5 | https://play.google.com/store/apps/details?id=com.nextbillion.groww | GROWW Play Store listing (review source) |
| 6 | https://microsoft.github.io/presidio | Presidio PII detection library |

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key for LLM calls |
| `APP_ID` | Yes | Play Store app ID (default: `com.nextbillion.groww`) |
| `WEEKS_BACK` | No | How many weeks of reviews to fetch (default: 12) |
| `MAX_REVIEWS` | No | Max usable reviews after filtering (default: 500) |
| `MIN_REVIEW_WORDS` | No | Discard reviews with fewer words (default: 5) |
| `GDOC_DOC_ID` | No | Google Doc ID from URL `/d/<ID>/edit` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | No | Path to service account JSON key file |
| `GMAIL_CLIENT_SECRET` | No | Path to Gmail OAuth2 client secret JSON |
| `GMAIL_TOKEN_PATH` | No | Path to save/load Gmail OAuth token |
| `EMAIL_TO` | No | Recipient email address for Gmail Draft |
| `FEE_FUND_URL` | No | URL to scrape fee explanation from |
| `USE_MCP` | No | `true` = MCP path, `false` = Direct API (default: false) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `SCRUB_MODE` | No | PII mode: `regex` or `presidio` (default: regex) |
