"""Acme Components mock ERP.

Like many real legacy ERPs: a read-only JSON API for integrations, writes only through the web UI.
Runs locally (sqlite) or on Vercel (set DATABASE_URL to a Postgres URL, e.g. Neon).
"""
import os
import re
import secrets
import time
from html import escape

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, UniqueConstraint,
                        create_engine, delete, insert, select, update)
from sqlalchemy.exc import IntegrityError

URL = os.environ.get("DATABASE_URL") or ("sqlite:////tmp/erp.db" if os.environ.get("VERCEL") else "sqlite:///erp.db")
URL = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", URL)
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
API_KEY = os.environ.get("ERP_API_KEY", "dev-key")
USER, PASSWORD = os.environ.get("ERP_USER", "ops"), os.environ.get("ERP_PASS", "ops123")

md = MetaData()
vendors = Table("vendors", md, Column("id", String, primary_key=True), Column("name", String, nullable=False))
pos = Table("purchase_orders", md, Column("po_number", String, primary_key=True),
            Column("vendor_id", String, nullable=False), Column("amount", Float, nullable=False))
# ponytail: Float money is fine for 2-decimal INR compared after round(); use Numeric if real ledgers come in.
invoices = Table("invoices", md, Column("id", Integer, primary_key=True, autoincrement=True),
                 Column("vendor_id", String, nullable=False), Column("invoice_number", String, nullable=False),
                 Column("po_number", String, nullable=False), Column("amount", Float, nullable=False),
                 Column("invoice_date", String), Column("idempotency_key", String, unique=True),
                 Column("created_at", Float, nullable=False), UniqueConstraint("vendor_id", "invoice_number"))
settings = Table("settings", md, Column("key", String, primary_key=True), Column("value", Integer))
sessions = Table("sessions", md, Column("token", String, primary_key=True), Column("created_at", Float))

VENDORS = [("V001", "Sharma Steel Pvt Ltd"), ("V002", "Kumar Logistics"), ("V003", "Patel Plastics"),
           ("V004", "Bharat Electricals")]
POS = [("PO-10441", "V001", 42300), ("PO-10442", "V002", 18500), ("PO-10443", "V003", 210000),
       ("PO-10444", "V004", 27000), ("PO-10445", "V001", 15600), ("PO-10446", "V003", 95000)]


def reset():
    with engine.begin() as c:
        for t in (invoices, pos, vendors, settings, sessions):
            c.execute(delete(t))
        c.execute(insert(vendors), [{"id": i, "name": n} for i, n in VENDORS])
        c.execute(insert(pos), [{"po_number": p, "vendor_id": v, "amount": a} for p, v, a in POS])
        # Already entered last week: the agent must detect the duplicate, not re-enter it.
        c.execute(insert(invoices).values(vendor_id="V001", invoice_number="INV-SS-2150", po_number="PO-10445",
                                          amount=15600, invoice_date="2026-09-28", idempotency_key="seed-1",
                                          created_at=0))


try:  # several serverless instances can cold-start at once; whoever loses the race just finds the data there
    md.create_all(engine)
    with engine.connect() as _c:
        empty = not _c.execute(select(vendors)).first()
    if empty:
        reset()
except Exception:
    md.create_all(engine)

app = FastAPI(title="Acme ERP")


def flag(key):
    with engine.connect() as c:
        return c.execute(select(settings.c.value).where(settings.c.key == key)).scalar() or 0


def require_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(401, "bad API key")


def logged_in(request: Request):
    token, ttl = request.cookies.get("erp_session"), flag("session_ttl")
    with engine.connect() as c:
        created = c.execute(select(sessions.c.created_at).where(sessions.c.token == token)).scalar()
    return created is not None and (not ttl or time.time() - created < ttl)


def page(title, body, status=200):
    css = ("body{font-family:system-ui;max-width:760px;margin:32px auto;padding:0 16px}"
           "label{display:block;margin:10px 0 4px}input,select{width:100%;padding:6px}"
           "button{margin-top:16px;padding:8px 16px}table{border-collapse:collapse;width:100%}"
           "td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}.err{color:#b00}")
    return HTMLResponse(f"<!doctype html><title>{title} · Acme ERP</title><style>{css}</style>"
                        f"<nav><b>Acme ERP</b> · <a href=/invoices>Invoices</a> · "
                        f"<a href=/invoices/new>New invoice</a></nav><h1>{title}</h1>{body}", status)


def slow():
    time.sleep(flag("slow_ms") / 1000)


@app.get("/")
def home():
    return RedirectResponse("/invoices")


@app.get("/login")
def login_form(next: str = "/invoices"):
    return page("Log in", f"<form method=post><input type=hidden name=next value='{escape(next)}'>"
                          "<label for=u>Username</label><input id=u name=username>"
                          "<label for=p>Password</label><input id=p name=password type=password>"
                          "<button>Log in</button></form>")


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), next: str = Form("/invoices")):
    if (username, password) != (USER, PASSWORD):
        return page("Log in", "<p class=err>Wrong username or password.</p>", 401)
    token = secrets.token_urlsafe()
    with engine.begin() as c:
        c.execute(insert(sessions).values(token=token, created_at=time.time()))
    r = RedirectResponse(next if next.startswith("/") else "/invoices", 303)
    r.set_cookie("erp_session", token, httponly=True)
    return r


@app.get("/invoices")
def list_invoices(request: Request):
    if not logged_in(request):
        return RedirectResponse("/login?next=/invoices", 303)
    with engine.connect() as c:
        rows = c.execute(select(invoices).order_by(invoices.c.id.desc())).mappings().all()
    trs = "".join(f"<tr><td><a href=/invoices/{r['id']}>{r['id']}</a><td>{escape(r['invoice_number'])}"
                  f"<td>{r['vendor_id']}<td>{escape(r['po_number'])}<td>₹{r['amount']:,.2f}" for r in rows)
    return page("Invoices", f"<table><tr><th>ID<th>Number<th>Vendor<th>PO<th>Amount{trs}</table>")


def invoice_form(error="", values=None):
    v = values or {}
    with engine.connect() as c:
        opts = "".join(f"<option value={i} {'selected' if v.get('vendor_id') == i else ''}>{escape(n)}</option>"
                       for i, n in c.execute(select(vendors.c.id, vendors.c.name)))
    fields = "".join(f"<label for={k}>{label}</label><input id={k} name={k} value='{escape(str(v.get(k, '')))}'>"
                     for k, label in [("invoice_number", "Invoice number"), ("po_number", "PO number"),
                                      ("amount", "Amount (INR)"), ("invoice_date", "Invoice date"),
                                      ("reference", "External reference")])
    button = ("<button id=post type=submit>Post to ledger</button>" if flag("rename_button")
              else "<button id=submit type=submit>Submit invoice</button>")
    modal = ("<div role=dialog aria-label=Notice style='position:fixed;inset:0;background:#0008;display:flex;"
             "align-items:center;justify-content:center'><div style='background:#fff;padding:24px'>"
             "System maintenance tonight at 22:00 IST. <button type=button "
             "onclick='this.closest(\"[role=dialog]\").remove()'>Dismiss</button></div></div>"
             if flag("modal") else "")
    err = f"<p class=err role=alert>{escape(error)}</p>" if error else ""
    return (f"{modal}{err}<form method=post action=/invoices><label for=vendor_id>Vendor</label>"
            f"<select id=vendor_id name=vendor_id>{opts}</select>{fields}{button}</form>")


@app.get("/invoices/new")
def new_invoice(request: Request):
    if not logged_in(request):
        return RedirectResponse("/login?next=/invoices/new", 303)
    slow()
    return page("New invoice", invoice_form())


@app.post("/invoices")
def create_invoice(request: Request, vendor_id: str = Form(...), invoice_number: str = Form(...),
                   po_number: str = Form(...), amount: float = Form(...), invoice_date: str = Form(""),
                   reference: str = Form(...)):
    if not logged_in(request):
        return RedirectResponse("/login?next=/invoices/new", 303)
    slow()
    if flag("fail_next_submit"):
        with engine.begin() as c:
            c.execute(update(settings).where(settings.c.key == "fail_next_submit")
                      .values(value=settings.c.value - 1))
        return page("Error", "<p class=err>500 Internal Server Error. Please try again.</p>", 500)
    values = dict(vendor_id=vendor_id, invoice_number=invoice_number, po_number=po_number, amount=amount,
                  invoice_date=invoice_date, reference=reference)
    if not re.fullmatch(r"PO-\d{5}", po_number):
        return page("New invoice", invoice_form("PO number must look like PO-12345.", values), 422)
    row = dict(values, idempotency_key=values.pop("reference"), created_at=time.time())
    try:
        with engine.begin() as c:
            if not c.execute(select(vendors.c.id).where(vendors.c.id == vendor_id)).first():
                return page("New invoice", invoice_form("Unknown vendor.", values), 422)
            new_id = c.execute(insert(invoices).values(**row)).inserted_primary_key[0]
    except IntegrityError:
        with engine.connect() as c:
            existing = c.execute(select(invoices.c.id).where(invoices.c.idempotency_key == reference)).scalar()
        if existing:  # same reference = same logical invoice: idempotent, return the original record
            return RedirectResponse(f"/invoices/{existing}", 303)
        return page("New invoice", invoice_form("Duplicate invoice number for this vendor.", values), 409)
    return RedirectResponse(f"/invoices/{new_id}", 303)


@app.get("/invoices/{invoice_id}")
def show_invoice(invoice_id: int, request: Request):
    if not logged_in(request):
        return RedirectResponse(f"/login?next=/invoices/{invoice_id}", 303)
    r = get_invoice(invoice_id)
    if not r:
        raise HTTPException(404)
    rows = "".join(f"<tr><th>{k}<td>{escape(str(v))}" for k, v in r.items())
    return page(f"Invoice saved #{invoice_id}", f"<table>{rows}</table>")


# ---------- read-only JSON API (X-API-Key) ----------

def get_invoice(invoice_id):
    with engine.connect() as c:
        return c.execute(select(invoices, vendors.c.name.label("vendor_name"))
                         .join(vendors, vendors.c.id == invoices.c.vendor_id)
                         .where(invoices.c.id == invoice_id)).mappings().first()


@app.get("/api/vendors", dependencies=[Depends(require_key)])
def api_vendors():
    with engine.connect() as c:
        return [dict(r) for r in c.execute(select(vendors)).mappings()]


@app.get("/api/purchase-orders/{po_number}", dependencies=[Depends(require_key)])
def api_po(po_number: str):
    with engine.connect() as c:
        r = c.execute(select(pos).where(pos.c.po_number == po_number)).mappings().first()
    if not r:
        raise HTTPException(404, "PO not found")
    return dict(r)


@app.get("/api/invoices", dependencies=[Depends(require_key)])
def api_invoices(vendor_id: str = None, invoice_number: str = None, idempotency_key: str = None,
                 since: float = None):
    q = select(invoices, vendors.c.name.label("vendor_name")).join(vendors, vendors.c.id == invoices.c.vendor_id)
    for col, val in [(invoices.c.vendor_id, vendor_id), (invoices.c.invoice_number, invoice_number),
                     (invoices.c.idempotency_key, idempotency_key)]:
        if val is not None:
            q = q.where(col == val)
    if since is not None:
        q = q.where(invoices.c.created_at >= since)
    with engine.connect() as c:
        return [dict(r) for r in c.execute(q).mappings()]


@app.get("/api/invoices/{invoice_id}", dependencies=[Depends(require_key)])
def api_invoice(invoice_id: int):
    r = get_invoice(invoice_id)
    if not r:
        raise HTTPException(404)
    return dict(r)


@app.post("/api/admin/reset", dependencies=[Depends(require_key)])
def api_reset():
    reset()
    return {"ok": True}


@app.post("/api/admin/chaos", dependencies=[Depends(require_key)])
def api_chaos(flags: dict[str, int]):
    """Failure injection: fail_next_submit, rename_button, modal, session_ttl (s), slow_ms."""
    with engine.begin() as c:
        c.execute(delete(settings).where(settings.c.key.in_(list(flags))))
        c.execute(insert(settings), [{"key": k, "value": v} for k, v in flags.items()])
    return flags
