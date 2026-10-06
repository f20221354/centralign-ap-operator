# Before real production (not needed for the prototype)

- Real auth for the console (SSO) and per-user approval authority.
- Secrets manager instead of env vars; a scoped ERP service account.
- Postgres for run state; a worker queue instead of threads; restartable workers.
- PII handling and retention for invoices and screenshots.
- Alerting on VERIFICATION_FAILED and RUN_ERROR.
- Deterministic second check of extraction (e.g. a parser for known vendor templates).
