"""Deterministic policy gate. The LLM proposes actions; only this code decides whether they run.

No LLM here on purpose: a prompt-injected model cannot argue its way past an if-statement.
"""
import hashlib
import json
import re

from agent.store import COMPANY

PERMS = json.loads((COMPANY / "permissions.json").read_text())


def norm(s):
    return re.sub(r"\W", "", s).casefold()


def snapshot(*facts):
    """Fingerprint of the facts a human approved; re-checked right before execution (TOCTOU)."""
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def check(tool, args, facts, erp):
    """-> (decision, reason, snapshot). decision is ALLOW, DENY or APPROVE (needs a human first).

    `facts` = what the runtime itself extracted from each invoice file, not what the model claims.
    """
    if tool not in PERMS["allowed_tools"]:
        return "DENY", f"'{tool}' is not permitted for this agent", None
    if tool != "create_invoice":
        return "ALLOW", "", None

    f = facts.get(args.get("file"))
    if not f:
        return "DENY", "read_invoice must be run on this file first", None
    vendor = next((v for v in erp.vendors() if v["id"] == args["vendor_id"]), None)
    if not vendor or norm(vendor["name"]) != norm(f["vendor_name"]):
        return "DENY", f"vendor {args['vendor_id']} does not match '{f['vendor_name']}' on the invoice", None
    if args["invoice_number"] != f["invoice_number"] or round(args["amount"], 2) != round(f["total_amount"], 2):
        return "DENY", "invoice number or amount differs from the invoice document", None
    if re.sub(r"\D", "", args["po_number"]) != re.sub(r"\D", "", f["po_number"]):
        return "DENY", "PO number differs from the invoice document", None
    po = erp.po(args["po_number"])
    if not po:
        return "DENY", f"PO {args['po_number']} not found in ERP", None
    if po["vendor_id"] != args["vendor_id"]:
        return "DENY", f"PO {po['po_number']} belongs to another vendor", None
    if abs(po["amount"] - f["total_amount"]) > PERMS["po_tolerance"] * po["amount"]:
        return "DENY", f"invoice ₹{f['total_amount']:,.2f} vs PO ₹{po['amount']:,.2f}: outside 2% tolerance", None
    if erp.find_invoice(args["vendor_id"], args["invoice_number"]):
        return "DENY", "duplicate: this vendor + invoice number is already in the ERP", None
    snap = snapshot(args, po)
    if f["total_amount"] > PERMS["approval_threshold_inr"]:
        return "APPROVE", (f"₹{f['total_amount']:,.2f} is above ₹{PERMS['approval_threshold_inr']:,} "
                           "and needs finance manager approval"), snap
    return "ALLOW", "", snap
