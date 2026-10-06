# Architecture

```
 Operator Console (localhost)            Vercel
 ┌──────────────────────────┐   ┌───────────────────────┐
 │ goal · live trace ·      │   │ Acme ERP (FastAPI)     │
 │ approve/answer · report  │   │  UI: login, invoices,  │
 └────────────┬─────────────┘   │      new-invoice form  │
              │                 │  API: vendors, POs,     │
 ┌────────────▼─────────────┐   │       invoices (read)   │
 │ Runtime                  │   │  admin: reset, chaos    │
 │  LLM (plan/act) ──► Policy gate ──► Executor ──────►│  Postgres (Neon)       │
 │       ▲                  │      browser (writes) / API (reads) / files
 │       └── Observation ◄── Classifier: SUCCESS / TRANSIENT / AUTH / BUSINESS / UNKNOWN
 │  Event log · Human requests · Lessons (sqlite/JSON)    │
 └────────────┬─────────────┘   └───────────────────────┘
              ▼
   Independent Verifier (re-reads PDFs, queries ERP API) → report.md + screenshots
```

Writes go through the UI and checks go through the API, so the verifier reads from a different channel
from the one the agent wrote through.
