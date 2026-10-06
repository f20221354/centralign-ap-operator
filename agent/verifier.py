"""Independent verification. Never trusts the agent's own claims or memory: re-reads every PDF from
scratch and checks the ERP's real state through its API (a different channel from the UI the agent wrote to).
"""
import re

from agent import store
from agent.policy import norm
from agent.store import COMPANY
from agent.tools import ERP, extract_invoice


def digits(s):
    return re.sub(r"\D", "", s)


def verify(run_id, started_at, extract=extract_invoice, erp=None):
    erp = erp or ERP()
    vendor_ids = {norm(v["name"]): v["id"] for v in erp.vendors()}
    checks, entered = [], set()

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    for pdf in sorted((COMPANY / "processed").glob("*.pdf")):
        f = extract(pdf)
        vid = vendor_ids.get(norm(f["vendor_name"]))
        rec = vid and erp.find_invoice(vid, f["invoice_number"])
        entered.add((vid, f["invoice_number"]))
        check(f"{pdf.name}: in ERP", rec, f"ERP #{rec['id']}" if rec else "no ERP record")
        if rec:
            check(f"{pdf.name}: amount matches", round(rec["amount"], 2) == round(f["total_amount"], 2),
                  f"PDF ₹{f['total_amount']:,.2f} / ERP ₹{rec['amount']:,.2f}")
            check(f"{pdf.name}: PO matches", digits(rec["po_number"]) == digits(f["po_number"]),
                  f"PDF {f['po_number']} / ERP {rec['po_number']}")

    for pdf in sorted((COMPANY / "flagged").glob("*.pdf")):
        f = extract(pdf)
        vid = vendor_ids.get(norm(f["vendor_name"]))
        rec = vid and erp.find_invoice(vid, f["invoice_number"])
        reason = (COMPANY / "flagged" / f"{pdf.name}.reason.txt")
        check(f"{pdf.name}: flagged, not entered by this run", not rec or rec["created_at"] < started_at,
              reason.read_text() if reason.exists() else "")

    left = sorted(p.name for p in (COMPANY / "inbox").glob("*.pdf"))
    check("inbox fully processed", not left, ", ".join(left))
    created = erp.invoices(since=started_at)
    rogue = [r for r in created if (r["vendor_id"], r["invoice_number"]) not in entered]
    check("no unauthorized ERP writes", not rogue, ", ".join(f"#{r['id']}" for r in rogue))
    check("no duplicate ERP records", len(created) == len({(r["vendor_id"], r["invoice_number"]) for r in created}))
    return {"passed": all(c["ok"] for c in checks), "checks": checks,
            "entered": sorted(p.name for p in (COMPANY / "processed").glob("*.pdf")),
            "flagged": sorted(p.name for p in (COMPANY / "flagged").glob("*.pdf"))}


def report(run_id, result, summary):
    evs = store.events(run_id)
    count = lambda t: sum(e["type"] == t for e in evs)
    lines = [f"# Run {run_id}: {'VERIFIED' if result['passed'] else 'VERIFICATION FAILED'}", "",
             f"**Goal:** {store.run(run_id)['goal']}", "", f"**Agent summary:** {summary or '(did not finish)'}", "",
             "## Verification (independent of the agent)", "", "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {c['check']} | {'✅' if c['ok'] else '❌'} | {c['detail']} |" for c in result["checks"]]
    lines += ["", "## What happened", "",
              f"- Entered: {', '.join(result['entered']) or 'none'}",
              f"- Flagged: {', '.join(result['flagged']) or 'none'}",
              f"- Actions proposed: {count('ACTION_PROPOSED')}, denied by policy: "
              f"{sum(e['type'] == 'POLICY_EVALUATED' and e['data']['decision'] == 'DENY' for e in evs)}",
              f"- Human requests: {count('HUMAN_REQUESTED')}, retries: {count('RETRY_SCHEDULED')}, "
              f"UI adaptations: {count('INTERFACE_ADAPTED')}, crash reconciliations: {count('RECONCILED')}", "",
              "## Human decisions", ""]
    lines += [f"- {e['data']['question']} → **{a['data']['status']}** {a['data']['answer'] or ''}"
              for e in evs if e["type"] == "HUMAN_REQUESTED"
              for a in evs if a["type"] == "HUMAN_ANSWERED" and a["data"]["request_id"] == e["data"]["request_id"]]
    lines += ["", "## Evidence (screenshots)", ""]
    lines += [f"- {e['data']['file']} → ERP #{e['data'].get('erp_id')}: ![]({e['data']['screenshot']})"
              for e in evs if e["type"] == "ACTION_COMPLETED" and e["data"].get("screenshot")]
    lines += ["", f"Full event log: `runs/runs.db` (run_id `{run_id}`, {len(evs)} events)."]
    return "\n".join(lines)
