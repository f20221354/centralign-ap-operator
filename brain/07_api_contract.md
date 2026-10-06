# ERP API contract (X-API-Key header)

- `GET /api/vendors` → `[{id, name}]`
- `GET /api/purchase-orders/{po_number}` → `{po_number, vendor_id, amount}` | 404
- `GET /api/invoices?vendor_id&invoice_number&idempotency_key&since` → `[invoice + vendor_name]`
- `GET /api/invoices/{id}`
- `POST /api/admin/reset` · `POST /api/admin/chaos {fail_next_submit, rename_button, modal, session_ttl, slow_ms}`

UI write: `POST /invoices` (form: vendor_id, invoice_number, po_number `PO-12345`, amount, invoice_date,
reference) → 303 to `/invoices/{id}` | 422 validation | 409 duplicate | 500 (chaos). Same `reference` ⇒ same record.
