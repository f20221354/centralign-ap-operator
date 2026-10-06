# Testing

- `tests/test_core.py` (no LLM): 5 concurrent submits with the same reference → 1 record; duplicate number
  → 409; PO format → 422; chaos 500 then success; policy allow/deny/approve/TOCTOU snapshot; injected
  amount denied; verifier fails a claimed-but-missing record.
- End-to-end + chaos + security + crash: `evals/run.py` against the real ERP and your LLM chain.
