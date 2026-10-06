"""Run state: append-only event log + human requests (approvals/questions) in sqlite, lessons in JSON."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPANY = ROOT / "company"
RUNS = ROOT / "runs"
RUNS.mkdir(exist_ok=True)
DB = RUNS / "runs.db"
LESSONS = COMPANY / "lessons.json"
MAX_LESSONS = 20


def q(sql, *args):
    with sqlite3.connect(DB) as c:  # connection per call: thread-safe, no pool to manage
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute(sql, args)]


q("create table if not exists runs(id text primary key, goal text, status text, started real)")
q("create table if not exists events(id integer primary key, run_id text, ts real, type text, data text)")
q("create table if not exists requests(id integer primary key, run_id text, kind text, question text,"
  " status text default 'PENDING', answer text)")


def new_run(goal):
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    q("insert into runs values(?,?,?,?)", run_id, goal, "RUNNING", time.time())
    (RUNS / run_id).mkdir()
    return run_id


def run(run_id):
    return q("select * from runs where id=?", run_id)[0]


def set_status(run_id, status):
    q("update runs set status=? where id=?", status, run_id)


def event(run_id, type, **data):
    q("insert into events(run_id, ts, type, data) values(?,?,?,?)", run_id, time.time(), type,
      json.dumps(data, default=str))
    print(f"[{run_id}] {type} {json.dumps(data, default=str)[:200]}", flush=True)


def events(run_id, after=0):
    return [dict(e, data=json.loads(e["data"]))
            for e in q("select * from events where run_id=? and id>? order by id", run_id, after)]


def ask(run_id, kind, question, auto=None):
    """Block until a human answers (console), or answer immediately with `auto` (evals)."""
    rid = q("insert into requests(run_id, kind, question) values(?,?,?) returning id", run_id, kind, question)[0]["id"]
    event(run_id, "HUMAN_REQUESTED", request_id=rid, kind=kind, question=question)
    if auto is not None:
        q("update requests set status=?, answer=? where id=?", *auto, rid)
    while (r := q("select * from requests where id=?", rid)[0])["status"] == "PENDING":
        time.sleep(1)
    event(run_id, "HUMAN_ANSWERED", request_id=rid, status=r["status"], answer=r["answer"])
    return r["status"], r["answer"]


def answer(request_id, status, text=""):
    q("update requests set status=?, answer=? where id=? and status='PENDING'", status, text, request_id)


def lessons():
    return json.loads(LESSONS.read_text()) if LESSONS.exists() else []


def add_lessons(new):
    merged = list(dict.fromkeys(lessons() + new))[-MAX_LESSONS:]  # dedupe, keep memory bounded
    LESSONS.write_text(json.dumps(merged, indent=2))
