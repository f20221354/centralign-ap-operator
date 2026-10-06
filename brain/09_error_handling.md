# Error handling (agent/tools.py `classify`, agent/runtime.py `t_create_invoice`)

| Outcome | Example | Route |
|---|---|---|
| TRANSIENT | HTTP 500, timeout | retry same action, exponential backoff, max 4 |
| AUTH | redirected to /login | log in again, retry |
| Interface change | "Submit invoice" button missing | the LLM maps intent to the new control (INTERFACE_ADAPTED) |
| BUSINESS | 422 bad PO format, 409 duplicate | error back to the LLM → it replans (fix input / flag) |
| Policy DENY | PO mismatch, duplicate, unknown vendor | the LLM flags the invoice with the reason |
| UNKNOWN | unexpected page | reconcile: look up the idempotency key in the ERP before anything else |
| Crash | process died after submit | `--resume`: STARTED-without-COMPLETED actions reconciled against the ERP |
