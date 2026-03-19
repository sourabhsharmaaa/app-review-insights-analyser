# GROWW Weekly Pulse — Detailed Architecture

## Problem Statement

GROWW is an Indian investment/stock app. Product, Support, and Leadership teams need a fast weekly health check on what users are saying in Play Store reviews — without reading hundreds of reviews manually.

**Solution:** An automated pipeline that scrapes recent Play Store reviews, groups them into themes using an LLM, generates a one-page weekly pulse note, and emails it to stakeholders — with zero PII in any output.

---

## Target Audience

| Team | What They Get |
|---|---|
| Product / Growth | Top themes + action ideas → know what to fix next |
| Support | Real user language + sentiment → acknowledge known issues |
| Leadership | Weekly health pulse → rating trends + top concerns at a glance |

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| LLM | Groq API (`llama-3.3-70b-versatile`) |
| Review Source | `google-play-scraper` (unofficial Play Store scraper) |
| PII Filtering | `presidio-analyzer` + `presidio-anonymizer` + `spacy en_core_web_sm` |
| Data Validation | `pydantic` v2 |
| Email Dispatch | Gmail API (`google-api-python-client`) — creates draft, no auto-send |
| **Web UI** | **React** (Vite, real-time SSE progress, internal dashboard) |
| CLI | `click` |
| Resilience | `tenacity` (retry + backoff) |
| Config | `python-dotenv` |
| Testing | `pytest` + `pytest-mock` |

---

## Project Directory Structure

```
app-review-insights-analyser/
│
├── .env                           # Secrets (gitignored)
├── .env.example                   # Template with all required vars
├── .gitignore
├── requirements.txt
├── ARCHITECTURE.md                # This file
├── README.md
│
├── main.py                        # CLI entrypoint (Click commands)
│
├── config/
│   └── settings.py                # Centralised config loaded from .env
│
├── pipeline/
│   ├── __init__.py
│   └── runner.py                  # Shared orchestration logic — called by BOTH CLI and UI
│
├── scraper/
│   ├── __init__.py
│   ├── models.py                  # Review & ScrapedBatch Pydantic models
│   └── play_store.py              # Fetch + paginate reviews; drop userName immediately
│
├── processor/
│   ├── __init__.py
│   ├── pii_filter.py              # Presidio-based PII scrubbing (content gate)
│   └── deduplicator.py            # SHA256-based dedup across overlapping week windows
│
├── analyser/
│   ├── __init__.py
│   ├── theme_generator.py         # LLM Call 1 — generate 3-5 theme labels
│   ├── theme_grouper.py           # LLM Call 2 — classify each review to a theme
│   └── pulse_builder.py           # LLM Call 3 — produce final PulseNote JSON
│
├── reporter/
│   ├── __init__.py
│   ├── formatter.py               # Render PulseNote + FeeExplanation → plain text + HTML
│   ├── email_sender.py            # Gmail API draft creation (includes fee section)
│   └── templates/
│       └── pulse_email.html       # Jinja2 inline-style email template (fee section added)
│
├── phase4/
│   ├── __init__.py
│   ├── formatter.py               # Canonical formatter (reporter/ delegates here)
│   ├── email_sender.py            # Canonical email sender (reporter/ delegates here)
│   ├── fee_scraper.py             # NEW: scrapes exit load from fund URL → FeeExplanation
│   ├── gdoc_reporter.py           # NEW: appends combined JSON to Google Doc via MCP
│   └── templates/
│       └── pulse_email.html       # Jinja2 template (fee section)
│
├── storage/
│   ├── __init__.py
│   └── cache.py                   # JSON file cache (idempotent re-runs per ISO week)
│
├── ui/                            # Streamlit web UI
│   ├── __init__.py
│   ├── app.py                     # Streamlit entrypoint (streamlit run ui/app.py)
│   └── components/
│       ├── pulse_preview.py       # Renders PulseNote inline in the UI
│       └── progress_tracker.py   # Step-by-step pipeline progress display
│
├── data/                          # Runtime data (gitignored)
│   ├── raw/                       # Scraped reviews — reviews_YYYY-WW.json
│   ├── processed/                 # PII-scrubbed reviews — reviews_clean_YYYY-WW.json
│   ├── reports/                   # Pulse notes — pulse_YYYY-WW.json / .txt / .html / combined_YYYY-WW.json
│   └── logs/                      # pulse.log, cron.log
│
└── tests/
    ├── test_scraper.py
    ├── test_pii_filter.py
    ├── test_analyser.py
    ├── test_email_sender.py
    └── test_runner.py
```

---

## End-to-End Data Flow

```
  ┌──────────────────────┐        ┌─────────────────────────────┐
  │   CLI  (main.py)     │        │   Web UI  (ui/app.py)        │
  │   python main.py run │        │   streamlit run ui/app.py    │
  └──────────┬───────────┘        └──────────────┬──────────────┘
             │                                   │
             └──────────────┬────────────────────┘
                            │  both call the same function
                            ▼
                  pipeline/runner.py
                  run_pipeline(weeks_back, send_email,
                               progress_callback=None)
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PLAY STORE                               │
│              (google-play-scraper, com.groww.app)               │
└─────────────────────────┬───────────────────────────────────────┘
                          │  rating, title, text, date
                          │  ⚠ userName is DROPPED HERE (never stored)
                          ▼
               scraper/play_store.py
               Date-window filter (last 8–12 weeks)
               Pagination loop with rate limiting
                          │
                          ▼
                  storage/cache.py
                          │
                          ▼
           data/raw/reviews_YYYY-WW.json
                          │
                          │
           ╔══════════════▼══════════════╗
           ║     SECURITY GATE — PII     ║
           ║   processor/pii_filter.py   ║
           ║  Presidio: PERSON, PHONE,   ║
           ║  EMAIL, PAN, AADHAAR → tags ║
           ╚══════════════╤══════════════╝
                          │
                          ▼
        data/processed/reviews_clean_YYYY-WW.json
                          │
               ┌──────────┴──────────┐
               ▼                     │
  ┌─────────────────────┐            │
  │  LLM CALL 1         │            │
  │  theme_generator    │            │
  │  → 3–5 theme labels │            │
  └──────────┬──────────┘            │
             ▼                       │
  ┌─────────────────────┐            │
  │  LLM CALL 2         │            │
  │  theme_grouper      │            │
  │  Batches of 40      │            │
  │  → {review: theme}  │            │
  └──────────┬──────────┘            │
             ▼                       ▼
  ┌─────────────────────┐
  │  LLM CALL 3         │
  │  pulse_builder      │
  │  → PulseNote JSON   │
  └──────────┬──────────┘
             │
             ▼
     data/reports/pulse_YYYY-WW.json
             │
             ├─────────────────────────────────────┐
             │                                     │
             ▼                                     ▼
   reporter/formatter.py                  ui/components/
   Jinja2 → .txt + .html                 pulse_preview.py
             │                           Renders inline in
             ▼                           Streamlit dashboard
   reporter/email_sender.py
   Gmail API draft creation
   [triggered by UI button OR CLI flag]
             │
             ▼
  ┌───────────────────────────────┐
  │  Gmail Draft (Gmail API)      │
  │  Product · Support · Leadership│
  └───────────────────────────────┘
```

---

## Phase 0 — Shared Pipeline Orchestration Layer

**Goal:** Extract all orchestration logic into `pipeline/runner.py` so both the CLI (`main.py`) and the Web UI (`ui/app.py`) call the exact same code path. No duplicate logic, no divergence.

### `pipeline/runner.py`

```python
def run_pipeline(
    weeks_back: int = 10,
    send_email: bool = False,
    force: bool = False,
    progress_callback: Callable[[str, int], None] | None = None,
) -> PulseNote:
    """
    Orchestrates all phases end-to-end.
    progress_callback(step_label, pct_complete) is called after each phase.
    Used by Streamlit to update the live progress bar.
    Returns the PulseNote (whether freshly generated or loaded from cache).
    """
```

**Steps inside `run_pipeline`:**

```
1. Determine current ISO week label
2. [SCRAPE]   — skip if already_scraped and not force
3. [PROCESS]  — skip if already_processed and not force
4. [ANALYSE]  — skip if already_analysed and not force
5. [REPORT]   — always render; skip email unless send_email=True
6. Return PulseNote
```

Each step calls `progress_callback("Scraping reviews…", 20)` etc., which Streamlit wires to `st.progress()` and the CLI ignores (callback is `None`).

**Why this layer exists:**
Before this layer, `main.py` contained all orchestration. When the UI was added, duplicating that logic would cause drift (e.g., idempotency skips only working in CLI). `runner.py` is the single source of truth for what the pipeline does and in what order.

---

## Phase 1 — Scraping & Data Models

**Goal:** Pull Play Store reviews reliably, enforce a clean data model, cache locally.

### `scraper/models.py`

```python
class Review(BaseModel):
    review_id: str          # SHA256(text + date) — stable dedup key
    rating: int             # 1–5
    text: str
    date: datetime
    thumbs_up: int = 0
    # userName : intentionally ABSENT — dropped at scrape time (PII gate)
    # title    : removed — not provided by google-play-scraper; not useful for analysis

class ScrapedBatch(BaseModel):
    app_id: str
    week_label: str         # ISO week: "2026-W12"
    scraped_at: datetime
    reviews: list[Review]
```

### `scraper/play_store.py`

- `fetch_reviews(app_id, weeks_back=12, max_reviews=500, min_review_words=5) -> list[Review]`
- Uses `google_play_scraper.reviews()` with `lang="en"`, `country="in"`, `sort=Sort.NEWEST`
- **Date cutoff computed at runtime:** `cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)` — always relative to today, never hardcoded
- Pagination via `continuation_token` loop, batches of 200
- Stops fetching when the oldest review in a batch predates `cutoff_date` **or** when the 3× buffer (`max_reviews × 3`) is reached — whichever comes first
- **English-only filter (applied at collection time):** reviews where fewer than 80% of alphabetic characters are ASCII are discarded — removes Hindi, Tamil, Marathi and other Indian-language reviews. No external dependency; uses Unicode code points only
- **Minimum word filter (applied at collection time):** reviews with fewer than `min_review_words` (default: 5) words are discarded as noise — removes single-word reviews like "good", "nice", "best" that carry no signal
- Both filters applied **before** the `max_reviews` cap — the cap counts only usable (English, ≥5 word) reviews
- If usable reviews exceed `max_reviews`, randomly sample down preserving rating distribution
- `userName` and `title` never stored — dropped at collection time
- `tenacity.retry(wait=wait_exponential(min=2, max=30), stop=stop_after_attempt(5))` around HTTP calls

### `storage/cache.py`

- `save_raw(batch) → data/raw/reviews_YYYY-WW.json`
- `load_raw(week_label) → ScrapedBatch | None`
- `already_scraped(week_label) → bool` — prevents duplicate scraping same ISO week

### CLI

```bash
python main.py scrape --weeks-back 10
```

**Output:** `data/raw/reviews_YYYY-WW.json`

---

## Phase 2 — PII Filtering & Pre-processing

**Goal:** Ensure zero PII reaches any LLM call, log file, or email. Two-layer approach.

### PII Removal Strategy

| Layer | What | Where |
|---|---|---|
| Structural | `userName` never stored | `scraper/models.py` — field absent from model |
| Structural | `title` not stored | removed from `Review` model — not provided by scraper |
| Content | Named entities scrubbed from `text` | `processor/pii_filter.py` |

### `processor/pii_filter.py`

- `scrub_review(review: Review) -> Review`
- Initialises `AnalyzerEngine` with `en_core_web_sm` NLP model
- Detects: `PERSON`, `PHONE_NUMBER`, `EMAIL_ADDRESS`, `LOCATION`, `IN_PAN`, `IN_AADHAAR`
- Replaces with typed tokens via `AnonymizerEngine`:
  - `Rahul` → `<PERSON>`
  - `9876543210` → `<PHONE>`
  - `user@gmail.com` → `<EMAIL>`
  - `1234 5678 9012` → `<ID>`
- `scrub_batch(reviews) -> list[Review]`
- `SCRUB_MODE=presidio|regex` env toggle — regex fallback covers Indian phone/PAN/Aadhaar patterns without spaCy

### `processor/deduplicator.py`

- `deduplicate(reviews) -> list[Review]` — deduplicates on `review_id`
- Matters when scraping windows overlap across weekly runs

### CLI

```bash
python main.py process --week 2024-W10
```

**Output:** `data/processed/reviews_clean_YYYY-WW.json`

---

## Phase 3 — LLM Analysis (3 Groq Calls)

**Goal:** Three sequential, focused LLM calls transforming clean reviews into a structured pulse.

### Why 3 Calls (Not 1 Mega-Prompt)

- Each call has a clear contract and can be independently retried or cached
- Smaller prompts → more reliable JSON output
- Token budget stays manageable across all Groq context limits

### Groq Free Tier Hard Limits

| Limit | Value |
|---|---|
| Requests per minute (RPM) | 30 |
| **Tokens per minute (TPM)** | **6,000** |
| Tokens per day (TPD) | 500,000 |

> These limits apply to `llama-3.3-70b-versatile` on the Groq free tier. The **6,000 TPM ceiling is the binding constraint** — not context length.

### Token Budget Per Call (safe under 6,000 TPM)

| Call | Input size | Tokens (est.) | Fits in 1 min? |
|---|---|---|---|
| Theme generation | **50** reviews × ~80 tokens + prompt | ~4,200 | ✅ yes |
| Theme grouping | **20** reviews/batch × ~80 tokens + prompt | ~2,000/batch | ✅ yes (with 20s wait) |
| Pulse building | 3 themes × 3 sample reviews + stats | ~1,500 | ✅ yes |

**With `MAX_REVIEWS=500` (default):**
- Theme grouping runs 25 batches of 20 (500 ÷ 20)
- Each batch ~2,000 tokens; with `wait_fixed(20)` between batches → 3 batches/min × 2,000 = 6,000 TPM exactly at limit
- Total grouping time: 25 batches × 20s = **~8 minutes**
- Total tokens for full pipeline run: ~4,200 + ~50,000 + ~1,500 = **~55,700 tokens** (< 500k daily limit)

> `MAX_REVIEWS=500` is the recommended default — statistically solid themes, ~8 min runtime. Lower to 200 for faster runs (~3 min). Only raise above 500 on a paid Groq tier where TPM limits are higher.

---

### LLM Call 1 — `analyser/theme_generator.py`

```
Input:  min(50, total_reviews) randomly sampled clean reviews (text only)
        50 reviews × ~80 tokens = ~4,000 tokens input → safe under 6,000 TPM
Model:  llama-3.3-70b-versatile
Temp:   0.2
Tokens: 256 max (just the labels)

System: "You are a product analyst for an Indian investment and stock trading app."
User:   "Given these {N} user reviews, identify 3 to 5 broad recurring themes.
         Return ONLY a JSON array of theme label strings.
         Example: ["Payment Failures", "KYC Friction", "App Performance"]"

Output: ["Payment & Transaction Failures", "KYC & Onboarding Issues",
         "Portfolio Display Bugs", "Customer Support"]
```

- Samples 50 reviews (not all reviews) — sufficient for theme discovery, token-safe
- Retries once with corrective prompt on JSON parse failure
- Returns `list[str]`

---

### LLM Call 2 — `analyser/theme_grouper.py`

```
Input:  All clean reviews (capped at MAX_REVIEWS=100), batched in groups of 20
        20 reviews × ~80 tokens + prompt (~400 tokens) ≈ 2,000 tokens/batch → safe under 6,000 TPM
        + theme labels from Call 1
Model:  llama-3.3-70b-versatile
Temp:   0.0  (deterministic classification)

System: "You are classifying app reviews into predefined themes."
User:   "Themes: {theme_list}
         For each review below, output a JSON object mapping
         review_index (int) to one theme label (exact string match).
         Reviews: {batch}"

Output per batch: {"0": "Payment & Transaction Failures", "1": "KYC & Onboarding Issues", ...}
```

- **Batch size: 20** (down from 40) — each batch stays well under 6,000 TPM
- **`wait_fixed(12)` between batches** — at 2,000 tokens/batch, 12s gap keeps throughput under the TPM ceiling even if multiple batches queue up
- With `MAX_REVIEWS=100`: 5 batches × 12s = ~60s total for this phase
- All batch results merged: `dict[theme_label, list[Review]]`
- Unrecognised labels → closest match by string similarity, else "Uncategorized" (never surfaced)
- On Groq 429 (rate limit hit): `tenacity` catches it, waits 30s, retries — does not crash the pipeline

---

### LLM Call 3 — `analyser/pulse_builder.py`

```
Input:  Top 3 themes by review count
        Per theme: count, avg_rating, % of total, 3 sample review texts
        3 themes × 3 reviews × ~80 tokens + stats/prompt (~500 tokens) ≈ 1,500 tokens total → safe
Model:  llama-3.3-70b-versatile
Temp:   0.4

System: "You are writing a weekly product health pulse for a fintech app.
         Keep the entire note (all summaries + action ideas combined) under 250 words."
User:   "Given these theme statistics and sample reviews, generate a PulseNote JSON:
         - one_line_summary per theme (max 15 words)
         - 3 user_quotes: verbatim from the reviews provided, no paraphrasing
         - 3 action_ideas: specific, evidence-grounded, actionable (max 30 words each)
         - Total word count across all text fields must be ≤250 words
         Return ONLY valid JSON matching the schema: {schema}"

Output: PulseNote JSON validated against Pydantic model
```

### `PulseNote` Pydantic Model

```python
class ThemeSummary(BaseModel):
    label: str
    review_count: int
    avg_rating: float
    pct_of_total: float
    one_line_summary: str

class PulseNote(BaseModel):
    week_label: str
    top_themes: list[ThemeSummary]   # exactly 3
    user_quotes: list[str]           # exactly 3, verbatim (PII already scrubbed)
    action_ideas: list[str]          # exactly 3, specific and actionable
    total_reviews_analysed: int
    avg_rating: float
    generated_at: datetime
```

- Pydantic validates LLM output; retries once on validation failure with schema reminder
- After 2 failures → `AnalysisError` raised → fallback to rule-based pulse (counts + ratings only)
- **Post-validation word count check:** after Pydantic passes, count total words across `one_line_summary` fields + `action_ideas`. If >250, retry once with `"Your response was {N} words. Shorten to ≤250 words total."` corrective prompt.

### CLI

```bash
python main.py analyse --week 2024-W10
```

**Output:** `data/reports/pulse_YYYY-WW.json`

---

## Phase 4 — Reporting & Email

**Goal:** Render PulseNote into a readable one-page note, enrich it with a Fee Explanation section scraped from a fund data source, and create a Gmail draft via the Gmail API.

---

### Feature 4A — Fee Explanation (NEW)

**Why:** GROWW users frequently complain about hidden fees (exit loads, brokerage charges). Appending a plain-language fee explanation to every weekly pulse gives leadership and support teams a ready reference — no manual research needed.

**What it scrapes:** Mutual Fund Exit Load details from a configurable fund page URL (e.g. INDMoney, AMFI, or Groww's own fund detail page).

#### `phase4/fee_scraper.py`

```python
class FeeExplanation(BaseModel):
    scenario: str                    # e.g. "Mutual Fund Exit Load"
    bullets: list[str]               # 3–5 plain-language facts about the fee
    source_links: list[str]          # URLs scraped from
    last_checked: date               # date of scrape (not cached weekly — always fresh)

def fetch_fee_explanation(fund_url: str) -> FeeExplanation:
    """
    Scrapes exit load details from fund_url.
    Parses the fee table / exit load section.
    Returns FeeExplanation with 3–5 bullet points.
    Uses httpx + BeautifulSoup. Retries 3× on network failure (tenacity).
    Falls back to a hardcoded FeeExplanation if scrape fails (non-fatal).
    """
```

**Scraping strategy:**
- `httpx.get(fund_url, headers={"User-Agent": ...})` — mimics browser to avoid bot blocks
- `BeautifulSoup` parses the response HTML
- Looks for keywords: `exit load`, `redemption`, `% if redeemed within`
- Extracts surrounding `<td>`, `<li>`, or `<p>` elements as bullet candidates
- LLM (Groq, same client) cleans and rephrases into 3–5 plain-language bullets (optional — can be skipped for speed)
- `FEE_FUND_URL` in `.env` — configurable per deployment

**Official source links (always exactly 2, pinned — Groww is the product so both links are Groww-official):**
```python
SOURCE_LINKS = [
    "https://groww.in/p/exit-load-in-mutual-funds",   # Groww's dedicated exit load explainer
    "https://groww.in/pricing",                         # Groww's official pricing/charges page
]
```
- These are hardcoded constants in `fee_scraper.py` — not scraped, not configurable
- Both are public, official Groww pages — no auth, no paywall
- AMFI is not used as a source because AMFI does not have a single dedicated exit load URL (their data is spread across per-scheme PDFs)
- `FEE_FUND_URL` in `.env` is used only for scraping the bullet content — the `source_links` field always uses the 2 pinned URLs above

**Fallback (if scrape fails):**
```python
FeeExplanation(
    scenario="Mutual Fund Exit Load",
    bullets=[
        "Exit load is a fee charged when you redeem mutual fund units before a specified holding period.",
        "Most equity mutual funds on Groww levy 1% exit load if redeemed within 12 months of purchase.",
        "Debt funds typically have 0–0.5% exit load for redemptions within 30–90 days.",
        "Exit load is deducted from the redemption NAV — it reduces the amount you receive.",
        "Each SIP instalment carries its own exit load clock from its individual purchase date.",
        "Exit load details are shown on each fund's page on Groww before you invest.",
    ],
    source_links=[
        "https://groww.in/p/exit-load-in-mutual-funds",
        "https://groww.in/pricing",
    ],
    last_checked=date.today(),
)
```

---

### `reporter/formatter.py`

- `render_text(pulse: PulseNote, fee: FeeExplanation | None = None) -> str`
- `render_html(pulse: PulseNote, fee: FeeExplanation | None = None) -> str`
- Template (`reporter/templates/pulse_email.html`): table-based layout, inline CSS only (email client compatibility — no external stylesheets, no CSS grid)
- Fee section appended **after** Action Ideas — clearly separated, labelled as informational

### One-Page Pulse Structure (with Fee Explanation)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GROWW Weekly Pulse | Week 2024-W10
  347 reviews analysed | Avg rating: 3.2 ★
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOP THEMES
──────────
1. Payment & Transaction Failures   142 reviews  2.1★  (41%)
   "Users report UPI payments stuck in pending state for 24–48 hours"

2. KYC & Onboarding Issues          89 reviews   2.8★  (26%)
   "Document re-upload loops blocking new account activation"

3. Portfolio Display Bugs           61 reviews   3.1★  (18%)
   "Unrealised P&L figures inconsistent with actual holdings"

WHAT USERS ARE SAYING
──────────────────────
❝ "My UPI payment has been pending for 2 days, no response from support" ❞
❝ "Had to upload PAN card 4 times, still says verification failed" ❞
❝ "The portfolio value shown is completely wrong, very stressful" ❞

ACTION IDEAS
────────────
1. Investigate UPI payment processing SLA — implement real-time status
   notifications to reduce support load and user anxiety.
2. Audit KYC document validation flow — identify top failure reasons
   and add inline guidance at each rejection point.
3. Cross-check portfolio calculation engine against live market data
   for the reported inconsistency cases.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FEE EXPLANATION: Mutual Fund Exit Load          ← NEW SECTION
──────────────────────────────────────────
• Exit load is charged when units are redeemed before the lock-in period ends.
• Most equity mutual funds on GROWW levy 1% if redeemed within 12 months.
• Debt funds typically have 0–0.5% exit load for redemptions within 30–90 days.
• Exit load is deducted from the redemption NAV — it reduces the amount credited.
• SIP instalments each carry their own exit load clock from their purchase date.

Source: https://www.indmoney.com/mutual-funds/hdfc-mid-cap-fund-...
Last checked: 2024-03-11

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generated: 2024-03-11 08:00 UTC
```

### `reporter/email_sender.py`

**Draft mode only — no auto-send.**

The requirement explicitly states "No auto-send." The email sender creates a Gmail draft that a human must open and send manually. This is enforced via the Gmail API (`drafts.create`), not `smtplib` (which would send immediately).

- `create_email_draft(pulse, fee, config) -> str` — returns the Gmail draft URL
- Builds `MIMEMultipart('alternative')` with `text/plain` fallback + `text/html` primary
- Subject: `Weekly Pulse + Fee Explainer — 2026-W12`
- `EMAIL_TO` pre-filled in the draft — human reviews recipients before sending
- Uses **Gmail API** (`google-api-python-client`) with OAuth2, not `smtplib`
- Draft appears in the sender's Gmail **Drafts folder** — no email is sent until a human clicks Send
- Logs draft URL on success; non-fatal if draft creation fails (report still saved to file)
- **Final PII gate:** Draft body contains only synthesized content — no raw review text

```python
# Gmail API draft creation (replaces smtplib)
from googleapiclient.discovery import build
import base64

def create_email_draft(pulse: PulseNote, fee: FeeExplanation, config: Settings) -> str:
    service = build("gmail", "v1", credentials=_get_credentials(config))
    message = _build_mime_message(pulse, fee, config)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}}
    ).execute()
    return f"https://mail.google.com/mail/#drafts/{draft['id']}"
```

**UI flow (approval-gated):**
```
Generate Pulse button → pipeline runs → pulse + fee ready → "Create Draft" button appears
→ user clicks "Create Draft" → draft created in Gmail → link shown in UI
→ user opens Gmail, reviews, clicks Send manually
```
The "Create Draft" button in the UI is the approval gate — nothing happens automatically.

### CLI

```bash
python main.py report --week 2024-W10 --send-email
python main.py report --week 2024-W10 --no-email    # save to file only
```

**Outputs:** `data/reports/pulse_YYYY-WW.txt`, `pulse_YYYY-WW.html`, email sent

---

### Feature 4B — Combined JSON Schema (NEW)

After the pulse and fee explanation are both ready, they are merged into a single `combined_YYYY-WW.json` file. This is the canonical output used by Feature 4C (Google Docs) and any future integrations.

```json
{
  "date": "2026-03-15",
  "weekly_pulse": {
    "week_label": "2026-W12",
    "themes": [
      { "label": "App Performance", "review_count": 50, "avg_rating": 3.9, "pct_of_total": 0.50, "one_line_summary": "..." }
    ],
    "quotes": ["Quote 1", "Quote 2", "Quote 3"],
    "action_ideas": ["Action 1", "Action 2", "Action 3"],
    "total_reviews_analysed": 100,
    "avg_rating": 3.2
  },
  "fee_scenario": "Mutual Fund Exit Load",
  "explanation_bullets": [
    "Exit load is charged when units are redeemed before the lock-in period ends.",
    "Most equity funds levy 1% if redeemed within 12 months.",
    "Exit load is deducted from the redemption NAV."
  ],
  "source_links": ["https://www.indmoney.com/mutual-funds/hdfc-mid-cap-fund-..."],
  "last_checked": "2026-03-15"
}
```

Saved to: `data/reports/combined_YYYY-WW.json`

---

### Feature 4C — Google Docs Append via MCP (NEW)

**Why:** Leadership teams often work in Google Docs/Sheets. Automatically appending each week's combined JSON to a shared Google Doc creates a living audit trail — no manual copy-paste, always up to date.

**How it works:**
- Uses the **Google Docs MCP server** (`@modelcontextprotocol/server-gdrive` or equivalent)
- After `combined_YYYY-WW.json` is written, `phase4/gdoc_reporter.py` calls the MCP tool to append a formatted section to a configured Google Doc

#### `phase4/gdoc_reporter.py`

```python
def append_to_gdoc(combined: dict, doc_id: str) -> str:
    """
    Appends a formatted weekly section to the Google Doc identified by doc_id.
    Uses Google Docs API via MCP (oauth2 credentials from .env).
    Returns the URL of the updated document.

    Section appended format:
    ─────────────────────────────────────
    GROWW Weekly Pulse — 2026-W12
    Date: 2026-03-15 | Reviews: 100 | Avg ★: 3.2
    Top Themes: App Performance (50%), Brokerage Charges (17%), Payment Failures (6%)
    Action Ideas: [1] ... [2] ... [3] ...
    Fee: Mutual Fund Exit Load
      • Bullet 1
      • Bullet 2
    Source: <link>
    ─────────────────────────────────────
    """
```

**Configuration (`.env`):**
```bash
GDOC_DOC_ID=your_google_doc_id_here          # from the Doc URL: /d/<DOC_ID>/edit
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...                      # obtained via OAuth2 flow once
```

**MCP Setup:**
```bash
# Install Google Docs MCP server
npx @modelcontextprotocol/server-gdrive

# Or use the Google API Python client directly (no MCP daemon needed):
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

**Append flow inside `runner.py`:**
```
6. [REPORT]    — render txt + html (existing)
7. [FEE]       — fetch_fee_explanation(FEE_FUND_URL)    ← NEW
8. [COMBINE]   — merge PulseNote + FeeExplanation → combined_YYYY-WW.json  ← NEW
9. [GDOC]      — append_to_gdoc(combined, GDOC_DOC_ID)  ← NEW (skipped if GDOC_DOC_ID not set)
10.[EMAIL]     — create_email_draft with fee section      ← updated
```

**Idempotency:** `gdoc_reporter` checks `storage/cache.py:already_reported(week_label)` before appending — prevents duplicate entries on re-runs.

---

## Phase 5 — Web UI (Streamlit Dashboard)

**Goal:** Give Product, Support, and Leadership teams a browser-based interface to trigger the pipeline, preview the one-page pulse inline, and send the email — no terminal access required.

### Why Streamlit

- Pure Python — no separate frontend codebase, no JS build step
- Built-in widgets: buttons, sliders, progress bars, expanders, download buttons
- Real-time streaming updates via `st.status()` / `st.progress()` during the pipeline run
- Ideal for internal tools; not intended as a public-facing web app

### How to Start

```bash
streamlit run ui/app.py
# Opens http://localhost:8501
```

---

### `ui/app.py` — Page Structure

The app has two pages (Streamlit multi-page via `st.navigation` or `pages/` folder):

#### Page 1: Generate Pulse

```
┌─────────────────────────────────────────────────────────┐
│  🌱 GROWW Weekly Pulse                                   │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  CONFIGURATION                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Weeks to analyse:  [────●────────────] 10        │   │
│  │ Email recipients:  [product@..., support@...]    │   │
│  │ Force re-run:      [ ] (skip cache)              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [ ▶  Generate Pulse ]                                  │
│                                                         │
│  ── PIPELINE PROGRESS ──────────────────────────────    │
│  ✅ Scraping reviews…          (85 reviews fetched)     │
│  ✅ Filtering PII…             (0 entities found)       │
│  ✅ Generating themes…         (4 themes identified)    │
│  ✅ Grouping reviews…          (3 batches processed)    │
│  ⏳ Building pulse note…                                │
│  [████████████████░░░░░░░░]  72%                        │
│                                                         │
│  ── PULSE PREVIEW ──────────────────────────────────    │
│  [pulse_preview component renders PulseNote here]       │
│                                                         │
│  [ 📧 Send Email ]   [ ⬇ Download PDF ]                 │
└─────────────────────────────────────────────────────────┘
```

#### Page 2: History

```
┌─────────────────────────────────────────────────────────┐
│  📋 Pulse History                                        │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  Week        Reviews   Avg ★   Top Theme          Action│
│  ─────────────────────────────────────────────────────  │
│  2024-W12    347       3.2     Payment Failures   [View]│
│  2024-W11    291       3.5     KYC Issues         [View]│
│  2024-W10    318       3.1     App Crashes        [View]│
│                                                         │
│  [View] → opens pulse preview panel + Resend Email btn  │
└─────────────────────────────────────────────────────────┘
```

---

### `ui/components/pulse_preview.py`

Renders a `PulseNote` object directly in the Streamlit UI using native widgets:

```python
def render_pulse(pulse: PulseNote) -> None:
    """Renders the full one-page pulse inside a Streamlit container."""
```

**Layout:**

```
st.metric row:   Total Reviews | Avg Rating | Week Label
st.divider
st.subheader:    "Top Themes"
  → For each ThemeSummary: st.expander with review count, avg rating, one-line summary
    and a horizontal bar showing % of total (rendered via st.progress)
st.divider
st.subheader:    "What Users Are Saying"
  → 3 st.info boxes with verbatim quotes
st.divider
st.subheader:    "Action Ideas"
  → st.markdown numbered list
st.caption:      "Generated at {timestamp}"
```

---

### `ui/components/progress_tracker.py`

Provides the `progress_callback` function passed to `pipeline/runner.py`:

```python
def make_progress_callback(
    status_container: st.delta_generator.DeltaGenerator,
    progress_bar: st.delta_generator.DeltaGenerator,
) -> Callable[[str, int], None]:
    """
    Returns a callback that updates Streamlit's status container
    and progress bar. Passed to runner.run_pipeline().
    """
    def callback(step_label: str, pct: int) -> None:
        status_container.write(f"⏳ {step_label}")
        progress_bar.progress(pct)
    return callback
```

**Pipeline step labels and percentages:**

| Step | Label shown in UI | % |
|---|---|---|
| 1 | Scraping Play Store reviews… | 15 |
| 2 | Filtering PII from review text… | 30 |
| 3 | Generating theme labels with Groq… | 50 |
| 4 | Grouping reviews by theme… | 70 |
| 5 | Building weekly pulse note… | 88 |
| 6 | Saving report… | 95 |
| 7 | Done ✅ | 100 |

---

### Create Draft Flow from UI

The **"Create Draft"** button in the UI is decoupled from pipeline generation:

```python
if st.button("📧 Create Draft"):
    with st.spinner("Creating draft…"):
        draft_url = create_email_draft(
            pulse=st.session_state.pulse,
            text_body=render_text(st.session_state.pulse),
            html_body=render_html(st.session_state.pulse),
            config=settings,
        )
    st.success(f"Draft created — open in Gmail to review and send: {draft_url}")
```

- User can generate the pulse, **review it in the UI first**, then decide to create a draft
- Prevents accidental email dispatch — no email is sent until the human clicks Send in Gmail
- `EMAIL_TO` is pre-populated from `.env` but editable in the UI config panel for one-off sends

---

### Download One-Pager from UI

```python
st.download_button(
    label="⬇ Download as Text",
    data=render_text(pulse),
    file_name=f"groww_pulse_{pulse.week_label}.txt",
    mime="text/plain",
)
```

Users can download the pulse as a `.txt` file to share in Slack or save locally without email.

---

### UI State Management

Streamlit re-runs the entire script on every interaction. State is preserved via `st.session_state`:

| Key | Type | Purpose |
|---|---|---|
| `st.session_state.pulse` | `PulseNote \| None` | Generated pulse; persists between button clicks |
| `st.session_state.pipeline_running` | `bool` | Prevents double-click re-runs |
| `st.session_state.last_run_week` | `str` | ISO week label of last successful run |

The pipeline runs in a `st.spinner` context on the main thread (no threading needed for a single-user internal tool).

---

### UI Security Note

- The config panel allows editing `EMAIL_TO` in the UI — this is intentional for ad-hoc sends to different stakeholders
- `GROQ_API_KEY`, `GOOGLE_CLIENT_SECRET` are **never displayed** in the UI (loaded from `.env` only)
- No authentication layer — this is an **internal-only tool** intended to be run locally or on a private network. If deployed on a shared server, add HTTP Basic Auth via a reverse proxy (nginx) or Streamlit's built-in `st.secrets` + a simple login gate.

---

## Phase 6 — Orchestration & Hardening

**Goal:** Single `run` command (CLI) / single button (UI), idempotency, scheduling, observability, graceful failures.

### Full CLI Surface (`main.py` via Click)

```bash
python main.py run     --weeks-back 10 --send-email    # full pipeline
python main.py scrape  --weeks-back 10
python main.py process --week 2024-W10
python main.py analyse --week 2024-W10
python main.py report  --week 2024-W10 [--send-email | --no-email]
python main.py status                                   # show all cached weeks

# UI
streamlit run ui/app.py                                 # launch web dashboard
```

### Idempotency

Each phase checks `storage/cache.py` for existing output before running:

```
run command
  ├── already_scraped(week)?     → skip scrape
  ├── already_processed(week)?   → skip PII filter
  ├── already_analysed(week)?    → skip LLM calls
  └── already_reported(week)?    → skip render (--force to override)
```

Safe to re-run after any failure — no duplicate API calls or emails.

### Scheduling (Weekly Cron)

```bash
# Add to crontab -e — runs every Monday at 8:00 AM
0 8 * * 1 cd /path/to/project && .venv/bin/python main.py run --send-email >> data/logs/cron.log 2>&1
```

### Logging

- All modules use `logging` (not `print`)
- Format: `%(asctime)s %(levelname)s %(name)s: %(message)s`
- `LOG_LEVEL` env var controls verbosity
- Rotating log file: `data/logs/pulse.log`

### Error Handling

| Failure | Behaviour |
|---|---|
| Play Store scrape returns 0 reviews | Raise `ScraperError` → send "scraping failed" alert email → exit |
| LLM JSON parse failure | Retry once with corrective prompt |
| 2× LLM failures | Raise `AnalysisError` → fall back to rule-based pulse (counts + ratings, no summaries) |
| Gmail API draft creation failure | Log error, save report to file, continue (non-fatal) |
| `google-play-scraper` network timeout | `tenacity` exponential backoff, 5 attempts max |

---

## Environment Configuration

### `.env.example`

```bash
# ── Groq ──────────────────────────────────────────────
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# ── App ───────────────────────────────────────────────
APP_ID=com.nextbillion.groww   # correct package ID — com.groww.app returns 404
WEEKS_BACK=12           # rolling window: always computed from today's date at runtime

# ── Token budget (Groq free tier: 6,000 TPM) ──────────
# Lower MAX_REVIEWS if you hit rate limits; raise it on a paid Groq plan
MAX_REVIEWS=500         # usable reviews (English, ≥5 words) sent to LLM

# ── Email ─────────────────────────────────────────────
# Gmail API creates a draft — no auto-send. Human reviews and sends manually.
EMAIL_FROM=yourname@gmail.com
EMAIL_TO=product@company.com,support@company.com,leadership@company.com

# ── Fee Explanation (Feature 4A) ──────────────────────
# URL of the mutual fund page to scrape exit load details from
FEE_FUND_URL=https://www.indmoney.com/mutual-funds/hdfc-mid-cap-fund-direct-plan-growth-option-3097

# ── Google Docs (Feature 4C) ───────────────────────────
# Doc ID from the Google Doc URL: docs.google.com/document/d/<DOC_ID>/edit
GDOC_DOC_ID=your_google_doc_id_here
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token   # obtained via OAuth2 once; see setup guide

# ── Optional ──────────────────────────────────────────
LOG_LEVEL=INFO
SCRUB_MODE=presidio          # or: regex (fallback if spaCy unavailable)
```

---

## Requirements

### `requirements.txt`

```
# Scraping
google-play-scraper==1.2.7
httpx>=0.27.0                    # fee_scraper HTTP client
beautifulsoup4>=4.12.0           # fee_scraper HTML parser

# Google APIs (Gmail draft + Google Docs append — Features 4B & 4C)
google-api-python-client>=2.120.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
# Note: smtplib removed — Gmail API used for draft creation (no auto-send)

# LLM
groq==0.11.0

# Config
python-dotenv==1.0.1

# Data validation
pydantic==2.7.1

# PII detection
presidio-analyzer==2.2.354
presidio-anonymizer==2.2.354
spacy==3.7.4
# After install: python -m spacy download en_core_web_sm

# Email templating
jinja2==3.1.4

# Resilience
tenacity==8.3.0

# CLI
click==8.1.7

# Web UI
streamlit==1.35.0

# Testing
pytest==8.2.2
pytest-mock==3.14.0
```

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
# Fill in GROQ_API_KEY and email credentials

# Option A — CLI
python main.py run --weeks-back 12 --send-email

# Option B — Web UI
streamlit run ui/app.py
# Opens http://localhost:8501
```

---

## Key Design Decisions

### 1. Three LLM Calls vs One Mega-Prompt
Splitting into (1) theme generation, (2) classification, (3) pulse writing gives each call a clear, small contract. It allows independent retries, simpler prompts, and more reliable structured JSON output. A single prompt for all three tasks would regularly fail or hallucinate theme assignments.

### 2. Two-Layer PII Architecture
- **Structural** (Layer 1): `userName` is never modelled. It cannot leak because the field does not exist anywhere in the codebase beyond the scraper's raw HTTP response.
- **Content** (Layer 2): Presidio scrubs named entities from free-text fields before any write to `data/processed/`. All downstream modules — LLM calls, formatter, email — only ever touch `data/processed/` data.

### 3. JSON File Cache Over a Database
A weekly batch job processing 200–500 reviews has no need for a database. JSON files in `data/` are inspectable, debuggable, and portable. The `storage/cache.py` abstraction decouples all other modules from storage, so swapping to SQLite or Postgres is a single-file change.

### 4. Pydantic for LLM Output Validation
LLMs can and do return malformed JSON. Pydantic v2 validates the `PulseNote` structure deterministically — catching missing fields, wrong types, out-of-range values. The retry-with-corrective-prompt pattern ("Your response was not valid JSON. Schema: ...") resolves most failures on the second attempt.

### 5. Streamlit for Internal UI (Not a Full Web App)
Streamlit is chosen because it is pure Python — no separate frontend codebase, no JS build toolchain, no API layer. The entire UI is ~200 lines of Python. It provides real-time progress updates, form widgets, and a download button out of the box. The tradeoff is it is single-user and not suitable for public deployment without an auth layer. For an internal team tool used by 3–10 people, this is the right level of complexity.

### 6. `MAX_REVIEWS` Cap and Token-Safe Batch Sizes
Groq's free tier limit is **6,000 tokens per minute** for `llama-3.3-70b-versatile`. Without a cap, a typical week of GROWW reviews (300–500 reviews) would send ~24,000–40,000 tokens to the grouping phase alone, triggering immediate 429s. The solution is a hard `MAX_REVIEWS=100` cap with random sampling (preserving rating distribution), batch size of 20, and 12-second waits between batches. This keeps each API call under 2,000 tokens and the full pipeline under the TPM ceiling. The tradeoff is lower statistical coverage, which is acceptable — 100 reviews from 8–10 weeks is still representative of user sentiment trends.

### 7. Rolling Date Window (Always Relative to Today)
The scrape window is computed as `datetime.now(UTC) - timedelta(weeks=WEEKS_BACK)` at runtime. This means every weekly run automatically covers the most recent 8–10 weeks without any manual date updates. There is no hardcoded date anywhere in the codebase.

### 8. `pipeline/runner.py` as Shared Orchestration
The `runner.py` module is the critical boundary between the pipeline logic and its invocation surface (CLI or UI). Without it, adding the UI would require duplicating idempotency logic, error handling, and phase-ordering in both `main.py` and `ui/app.py`. The `progress_callback` pattern allows the UI to receive live updates without the runner needing to know anything about Streamlit.

---

## File-by-File Responsibility Summary

| File | Responsibility |
|---|---|
| `config/settings.py` | Load all env vars; single source of truth for configuration |
| `pipeline/runner.py` | **Shared orchestration** — called by both CLI and UI; owns phase order, idempotency, error handling, progress callbacks |
| `scraper/models.py` | Define `Review` and `ScrapedBatch` Pydantic models; enforce `userName` absence |
| `scraper/play_store.py` | Paginate Play Store, filter by date window, drop PII structurally |
| `processor/pii_filter.py` | Presidio scrubbing — **security gate** before any downstream processing |
| `processor/deduplicator.py` | Dedup reviews across overlapping week windows |
| `analyser/theme_generator.py` | LLM Call 1 — produce 3–5 theme label strings |
| `analyser/theme_grouper.py` | LLM Call 2 — classify each review to a theme (batched) |
| `analyser/pulse_builder.py` | LLM Call 3 — produce validated `PulseNote` |
| `reporter/formatter.py` | Render `PulseNote` + `FeeExplanation` to plain text + Jinja2 HTML |
| `reporter/email_sender.py` | Gmail API draft creation; final PII gate on output; includes fee section |
| `phase4/fee_scraper.py` | Scrape exit load from fund URL → `FeeExplanation` bullets (NEW) |
| `phase4/gdoc_reporter.py` | Append `combined_YYYY-WW.json` to Google Doc via API (NEW) |
| `storage/cache.py` | JSON file cache; idempotency per ISO week label |
| `main.py` | Click CLI; thin wrapper over `pipeline/runner.py` |
| `ui/app.py` | Streamlit entrypoint; two pages: Generate Pulse + History |
| `ui/components/pulse_preview.py` | Renders `PulseNote` inline using Streamlit widgets |
| `ui/components/progress_tracker.py` | Produces `progress_callback` for live pipeline progress bar |
