# Phase 5 — React JS Web UI + FastAPI backend
#
# api.py        : FastAPI REST + SSE backend (called by the React frontend)
#
# React frontend lives in ui/ at the project root:
#   ui/src/pages/GeneratePulse.jsx   — trigger pipeline, live progress, pulse preview
#   ui/src/pages/History.jsx         — browse all cached weekly pulses
#   ui/src/components/PulsePreview.jsx
#   ui/src/components/ProgressTracker.jsx
#
# Start backend : uvicorn phase5.api:app --reload --port 8000
# Start frontend: cd ui && npm run dev   (proxies /api → localhost:8000)
