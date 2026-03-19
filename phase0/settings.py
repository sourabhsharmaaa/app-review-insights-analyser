from __future__ import annotations

# Phase 0 — canonical settings implementation.
# config/settings.py imports from here.

import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # ── Groq ──────────────────────────────────────────────────────────────────
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # ── App ───────────────────────────────────────────────────────────────────
    app_id: str = "com.nextbillion.groww"
    weeks_back: int = 12
    max_reviews: int = 500          # usable reviews after min_review_words filter
    min_review_words: int = 5       # reviews with fewer words are discarded as noise
    batch_wait_seconds: int = 20    # seconds between LLM grouping batches (TPM safety)

    # ── Google Docs (Phase 4C) ─────────────────────────────────────────────────
    gdoc_doc_id: str = ""                    # Doc ID from URL: /d/<DOC_ID>/edit — optional
    google_service_account_json: str = ""    # path to downloaded service account JSON key file

    # ── Optional ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    scrub_mode: str = "regex"       # "presidio" requires spaCy en_core_web_sm

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables / .env file."""
        groq_api_key = os.getenv("GROQ_API_KEY", "")
        if not groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and fill it in."
            )

        return cls(
            groq_api_key=groq_api_key,
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            app_id=os.getenv("APP_ID", "com.nextbillion.groww"),
            weeks_back=int(os.getenv("WEEKS_BACK", "12")),
            max_reviews=int(os.getenv("MAX_REVIEWS", "2000")),
            min_review_words=int(os.getenv("MIN_REVIEW_WORDS", "5")),
            batch_wait_seconds=int(os.getenv("BATCH_WAIT_SECONDS", "20")),
            gdoc_doc_id=os.getenv("GDOC_DOC_ID", ""),
            google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            scrub_mode=os.getenv("SCRUB_MODE", "regex"),
        )

    def configure_logging(self) -> None:
        """Apply log level from settings to the root logger."""
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
