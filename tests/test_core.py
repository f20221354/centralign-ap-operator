"""Checks for the parts that must never break: ERP idempotency, the policy gate, the verifier.
No LLM or network needed.   .venv/bin/python -m unittest -v
"""
import os
import tempfile
import threading
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/erp.db"
from fastapi.testclient import TestClient  # noqa: E402

from agent import policy, runtime, tools, verifier  # noqa: E402
from mock_erp import app as erp_app  # noqa: E402

FORM = dict(vendor_id="V001", invoice_number="INV-T-1", po_number="PO-10441", amount="42300",
            invoice_date="2026-10-01", reference="key-1")


def session():
    c = TestClient(erp_app.app)
    c.post("/login", data={"username": "ops", "password": "ops123"})
    return c


class ERPTest(unittest.TestCase):
    def setUp(self):
        erp_app.reset()

    def count(self):
        return len(erp_app.api_invoices(invoice_number="INV-T-1"))

    def test_concurrent_same_reference_creates_one_record(self):
        clients = [session() for _ in range(5)]
        threads = [threading.Thread(target=c.post, args=("/invoices",), kwargs={"data": FORM}) for c in clients]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(self.count(), 1)

    def test_same_number_new_reference_is_rejected(self):
        c = session()
        c.post("/invoices", data=FORM)
        self.assertEqual(c.post("/invoices", data=dict(FORM, reference="key-2")).status_code, 409)
        self.assertEqual(self.count(), 1)

    def test_po_format_and_chaos(self):
        c = session()
        self.assertEqual(c.post("/invoices", data=dict(FORM, po_number="PO 10441")).status_code, 422)
        erp_app.api_chaos({"fail_next_submit": 1})
        self.assertEqual(c.post("/invoices", data=FORM).status_code, 500)
        self.assertEqual(c.post("/invoices", data=FORM).status_code, 200)  # followed redirect to the record
        self.assertEqual(self.count(), 1)


class FakeERP:
    def __init__(self, po_amount=42300, existing=None):
        self.po_amount, self.existing = po_amount, existing

    def vendors(self):
        return [{"id": "V001", "name": "Sharma Steel Pvt Ltd"}]

    def po(self, n):
        return {"po_number": n, "vendor_id": "V001", "amount": self.po_amount} if n == "PO-10441" else None

    def find_invoice(self, vendor_id, number):
        return self.existing

    def invoices(self, **kw):
        return []


FACTS = {"a.pdf": {"vendor_name": "Sharma Steel Pvt Ltd", "invoice_number": "INV-1", "po_number": "PO 10441",
                   "total_amount": 42300}}
ARGS = dict(file="a.pdf", vendor_id="V001", invoice_number="INV-1", po_number="PO-10441", amount=42300,
            invoice_date="2026-10-01")


class PolicyTest(unittest.TestCase):
    def decide(self, args=ARGS, facts=FACTS, erp=None, tool="create_invoice"):
        return policy.check(tool, args, facts, erp or FakeERP())[0]

    def test_clean_invoice_allowed(self):
        self.assertEqual(self.decide(), "ALLOW")

    def test_tool_outside_permissions_denied(self):
        self.assertEqual(self.decide(tool="mark_invoice_paid"), "DENY")

    def test_model_cannot_change_the_amount(self):  # e.g. after a prompt injection
        self.assertEqual(self.decide(args=dict(ARGS, amount=4230)), "DENY")

    def test_po_mismatch_duplicate_and_unread_file_denied(self):
        self.assertEqual(self.decide(erp=FakeERP(po_amount=27000)), "DENY")
        self.assertEqual(self.decide(erp=FakeERP(existing={"id": 1})), "DENY")
        self.assertEqual(self.decide(facts={}), "DENY")

    def test_large_invoice_needs_approval_and_snapshot_tracks_facts(self):
        big = {"a.pdf": dict(FACTS["a.pdf"], total_amount=60000)}
        d, _, snap = policy.check("create_invoice", dict(ARGS, amount=60000), big, FakeERP(po_amount=60000))
        self.assertEqual(d, "APPROVE")
        _, _, snap2 = policy.check("create_invoice", dict(ARGS, amount=60000), big, FakeERP(po_amount=60500))
        self.assertNotEqual(snap, snap2)  # PO changed after approval -> approval no longer valid


class VerifierTest(unittest.TestCase):
    def test_claimed_but_missing_record_fails(self):
        root = Path(tempfile.mkdtemp())
        for d in ("inbox", "processed", "flagged"):
            (root / d).mkdir()
        (root / "processed" / "a.pdf").write_bytes(b"%PDF")
        verifier.COMPANY = root
        result = verifier.verify("r", 0, extract=lambda p: FACTS["a.pdf"], erp=FakeERP())
        self.assertFalse(result["passed"])  # the agent moved the file, but the ERP has no record


def rate_limit(retry_after):
    import httpx
    import openai
    resp = httpx.Response(429, headers={"retry-after": retry_after} if retry_after else {},
                          request=httpx.Request("POST", "http://x"))
    return openai.RateLimitError("rate limited", response=resp, body=None)


class FakeReply:
    usage = None
    choices = [type("C", (), {"message": "ok"})]


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.calls, self.slept = [], []
        tools.COOLDOWN.clear()
        self._call, self._sleep, self._chain = tools.call, tools.time.sleep, tools.CHAIN
        tools.time.sleep = self.slept.append
        tools.CHAIN = ["groq", "gemini"]
        os.environ.update(GROQ_API_KEY="x", GEMINI_API_KEY="y")

    def tearDown(self):
        tools.call, tools.time.sleep, tools.CHAIN = self._call, self._sleep, self._chain

    def use(self, behaviour):
        def fake(name, messages, tool_specs):
            self.calls.append(name)
            return behaviour(name)
        tools.call = fake

    def test_daily_quota_falls_through_to_next_provider(self):
        def b(name):
            if name == "groq":
                raise rate_limit("3600")
            return FakeReply()
        self.use(b)
        self.assertEqual(tools.llm([])[1], "gemini")
        self.assertEqual(self.calls, ["groq", "gemini"])
        self.assertEqual(self.slept, [])  # did not wait an hour

    def test_per_minute_limit_is_waited_out_on_same_provider(self):
        n = {"i": 0}

        def b(name):
            n["i"] += 1
            if n["i"] == 1:
                raise rate_limit("2")
            return FakeReply()
        self.use(b)
        self.assertEqual(tools.llm([])[1], "groq")
        self.assertEqual(len(self.slept), 1)

    def test_failed_provider_sits_out_instead_of_flapping(self):
        def b(name):
            if name == "groq":
                raise rate_limit("3600")
            return FakeReply()
        self.use(b)
        tools.llm([]); tools.llm([]); tools.llm([])
        self.assertEqual(self.calls, ["groq", "gemini", "gemini", "gemini"])  # groq tried once, then skipped

    def test_everything_rate_limited_waits_and_retries_instead_of_failing(self):
        n = {"i": 0}

        def b(name):
            n["i"] += 1
            if n["i"] <= 4:  # two full rounds of both providers limited, then quota refills
                raise rate_limit("")
            return FakeReply()
        self.use(b)
        self.assertEqual(tools.llm([])[1], "groq")
        self.assertGreaterEqual(len(self.slept), 2)  # it waited between rounds

    def test_all_providers_failing_raises_with_reasons(self):
        self.use(lambda name: (_ for _ in ()).throw(rate_limit("")))
        with self.assertRaisesRegex(RuntimeError, "groq.*gemini"):
            tools.llm([])


class ArgsTest(unittest.TestCase):
    def test_malformed_model_arguments_never_reach_the_gate(self):
        run = runtime.Run.__new__(runtime.Run)
        self.assertIn("__error", run.parse_args("create_invoice", "{not json"))
        self.assertIn("__error", run.parse_args("create_invoice", '{"file": "a.pdf"}'))
        self.assertIn("__error", run.parse_args("drop_database", "{}"))
        ok = run.parse_args("lookup_po", '{"po_number": "PO-10441"}')
        self.assertEqual(ok, {"po_number": "PO-10441"})
        self.assertEqual(run.parse_args("create_invoice", '{"file":"a","vendor_id":"V1","invoice_number":"I",'
                                        '"po_number":"P","amount":"42,300".replace(",","") ,"invoice_date":"d"}'
                                        .replace('"42,300".replace(",","") ', '"42300"'))["amount"], 42300.0)


class ConsoleAuthTest(unittest.TestCase):
    def test_password_gate(self):
        from agent import console
        c = TestClient(console.app)
        os.environ["CONSOLE_PASSWORD"] = "s3cret"
        try:
            self.assertEqual(c.get("/runs").status_code, 401)
            self.assertEqual(c.post("/runs", json={"goal": "x"}).status_code, 401)  # can't start runs unauthenticated
            self.assertEqual(c.get("/runs", auth=("anyone", "wrong")).status_code, 401)
            self.assertEqual(c.get("/runs", auth=("anyone", "s3cret")).status_code, 200)
        finally:
            del os.environ["CONSOLE_PASSWORD"]
        self.assertEqual(c.get("/runs").status_code, 200)  # unset = local, open


if __name__ == "__main__":
    unittest.main()
