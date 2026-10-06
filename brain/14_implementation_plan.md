# Implementation plan (as built, in one day)

1. Mock ERP: schema, seed, UI, read API, idempotency, chaos, Vercel-ready. ✅
2. Company context: SOP, permissions, 7 fixture invoices. ✅
3. Runtime: LLM tool loop, policy gate, event log. ✅
4. Executor: Playwright form submit, classifier, retry/re-auth/adapt/reconcile. ✅
5. HITL: approvals + questions with TOCTOU re-check. ✅
6. Crash recovery via idempotency key reconciliation. ✅
7. Verifier + evidence report + lessons. ✅
8. Console, tests, eval harness. ✅
9. Next: deploy ERP to Vercel + Neon, run evals with an API key, record a demo video.
