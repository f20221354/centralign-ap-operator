# TRD

- Python 3.12, FastAPI, SQLAlchemy (ERP), sqlite (run state), Playwright (browser), OpenAI-compatible chat API (Groq, Gemini, Ollama) with ordered failover.
- Mock ERP: HTML UI for writes, read-only JSON API, failure injection, sqlite locally / Postgres (Neon) on Vercel.
- Non-functional: deterministic authorisation, append-only history, idempotent writes, crash reconciliation,
  independent verification, bounded memory.
