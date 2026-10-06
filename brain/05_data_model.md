# Data model

ERP (`mock_erp/app.py`): `vendors(id, name)`, `purchase_orders(po_number, vendor_id, amount)`,
`invoices(id, vendor_id, invoice_number, po_number, amount, invoice_date, idempotency_key UNIQUE, created_at,
UNIQUE(vendor_id, invoice_number))`, `settings` (chaos flags), `sessions`.

Run state (`agent/store.py`): `runs(id, goal, status, started)`, `events(id, run_id, ts, type, data)`,
`requests(id, run_id, kind approval|question, question, status, answer)`.

Event types: GOAL_RECEIVED, AGENT_THOUGHT, ACTION_PROPOSED, POLICY_EVALUATED, HUMAN_REQUESTED, HUMAN_ANSWERED,
APPROVAL_INVALIDATED, ACTION_STARTED, OUTCOME_CLASSIFIED, RETRY_SCHEDULED, INTERFACE_ADAPTED, ACTION_COMPLETED,
OBSERVATION, RECONCILED, AGENT_FINISHED, RUN_VERIFIED / RUN_VERIFICATION_FAILED, LESSONS_LEARNED, RUN_ERROR.

Run status: RUNNING → VERIFIED | VERIFICATION_FAILED | FAILED.
