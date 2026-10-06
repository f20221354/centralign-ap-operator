"""Operator Console: give a goal, watch the live trace, answer approvals/questions, read the evidence.

  uvicorn agent.console:app --port 8000
"""
import base64
import os
import secrets
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import store
from agent.runtime import Run, reset_workspace
from agent.store import RUNS

app = FastAPI(title="CentrAlign Operator Console")
ACTIVE = {"thread": None}  # one run at a time: each run spends LLM quota and a browser's worth of memory


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """If CONSOLE_PASSWORD is set (it is when deployed), every request but /healthz needs it (HTTP Basic, any username).
    Unset = local use, open. Read per request so it can be set after import."""
    password = os.environ.get("CONSOLE_PASSWORD")
    if password and request.url.path != "/healthz":
        try:
            given = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().partition(":")[2]
        except ValueError:
            given = ""
        if not secrets.compare_digest(given.encode(), password.encode()):
            return Response("Password required", 401, headers={"WWW-Authenticate": 'Basic realm="Operator Console"'})
    return await call_next(request)


app.mount("/shots", StaticFiles(directory=RUNS), name="shots")


class Goal(BaseModel):
    goal: str


class Answer(BaseModel):
    status: str
    answer: str = ""


@app.post("/runs")
def start(g: Goal):
    if ACTIVE["thread"] and ACTIVE["thread"].is_alive():
        raise HTTPException(409, "A run is already in progress. Wait for it to finish.")
    run = Run(g.goal, headless=True)

    def target():
        try:
            run.start()
        except Exception as e:  # surface the failure in the trace instead of a silently dead thread
            run.log("RUN_ERROR", error=f"{type(e).__name__}: {e}")
            store.set_status(run.id, "FAILED")

    ACTIVE["thread"] = threading.Thread(target=target, daemon=True)
    ACTIVE["thread"].start()
    return {"run_id": run.id}


@app.get("/runs")
def runs():
    return store.q("select * from runs order by started desc limit 20")


@app.get("/runs/{run_id}/events")
def events(run_id: str, after: int = 0):
    return {"run": store.run(run_id), "events": store.events(run_id, after),
            "pending": store.q("select * from requests where run_id=? and status='PENDING'", run_id)}


@app.post("/requests/{request_id}")
def answer(request_id: int, a: Answer):
    store.answer(request_id, a.status, a.answer)
    return {"ok": True}


@app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def report(run_id: str):
    path = RUNS / run_id / "report.md"
    return path.read_text() if path.exists() else "Report not ready yet."


@app.post("/reset")
def reset():
    try:
        reset_workspace()
    except Exception as e:  # say what failed (e.g. ERP rejected the key) instead of a bare 500
        raise HTTPException(500, f"{type(e).__name__}: {e}")
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Operator Console</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e3e3e3;--card:#f7f7f5;--ok:#1a7f37;--bad:#c62828;--warn:#9a6700}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--muted:#999;--line:#333;--card:#1f1f1f;
--ok:#4ac26b;--bad:#ff6b6b;--warn:#d4a72c}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui;max-width:980px;margin:24px auto;padding:0 16px}
input,button{font:inherit;padding:8px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}
button{cursor:pointer}#goal{width:min(560px,100%)}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}
.ev{border-left:3px solid var(--line);padding:2px 10px;margin:4px 0;font-size:13px;overflow-wrap:anywhere}
.ev b{font-family:ui-monospace,monospace}.DENY,.ERR{border-color:var(--bad)}.OK{border-color:var(--ok)}
.WARN{border-color:var(--warn)}small{color:var(--muted)}pre{white-space:pre-wrap;font-size:13px}
.req{border:2px solid var(--warn)}img{max-width:100%}
</style>
<h1>CentrAlign Operator Console</h1>
<div class=row><input id=goal value="Process this week's vendor invoices">
<button onclick=go()>Start run</button><button onclick=reset()>Reset demo data</button>
<small id=msg></small></div>
<div id=pending></div><h3>Live trace</h3><div id=trace><small>No run yet.</small></div>
<h3>Report</h3><pre id=report></pre>
<script>
let run=null,last=0;
const tone=e=>{const d=JSON.stringify(e.data);return /DENY|error|FAILED/.test(d+e.type)?'ERR':
 /COMPLETED|VERIFIED|APPROVED/.test(d+e.type)?'OK':/RETRY|ADAPT|RECONCIL|HUMAN/.test(e.type)?'WARN':''};
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function go(){const r=await fetch('/runs',{method:'POST',headers:{'content-type':'application/json'},
 body:JSON.stringify({goal:goal.value})});if(!r.ok){msg.textContent=(await r.json()).detail||'could not start';return;}
 run=(await r.json()).run_id;last=0;trace.innerHTML='';report.textContent='';}
async function reset(){msg.textContent='resetting...';try{const r=await fetch('/reset',{method:'POST'});
 msg.textContent=r.ok?'demo data reset':'reset failed: '+r.status+' '+(await r.text()).slice(0,300);}catch(e){msg.textContent='reset failed: '+e;}}
async function answer(id,st){const a=document.getElementById('a'+id);await fetch('/requests/'+id,{method:'POST',
 headers:{'content-type':'application/json'},body:JSON.stringify({status:st,answer:a?a.value:''})});}
async function poll(){if(run){const d=await (await fetch(`/runs/${run}/events?after=${last}`)).json();
 msg.textContent=`run ${run}: ${d.run.status}`;
 for(const e of d.events){last=e.id;const shot=e.data.screenshot?`<br><img src="/shots/${run}/${e.data.screenshot}">`:'';
  trace.insertAdjacentHTML('beforeend',`<div class="ev ${tone(e)}"><b>${e.type}</b> <small>${new Date(e.ts*1000)
  .toLocaleTimeString()}</small><br>${esc(JSON.stringify(e.data)).slice(0,600)}${e.type=='ACTION_COMPLETED'?shot:''}</div>`);}
 pending.innerHTML=d.pending.map(p=>`<div class="card req"><b>${p.kind=='approval'?'Approval needed':'Question from the agent'}
  </b><p>${esc(p.question)}</p><div class=row><input id=a${p.id} placeholder="${p.kind=='approval'?'note (optional)':'your answer'}">
  ${p.kind=='approval'?`<button onclick="answer(${p.id},'APPROVED')">Approve</button><button onclick="answer(${p.id},'REJECTED')">Reject</button>`
  :`<button onclick="answer(${p.id},'ANSWERED')">Send</button>`}</div></div>`).join('');
 if(/VERIFIED|FAILED/.test(d.run.status)&&!report.textContent)report.textContent=await (await fetch(`/runs/${run}/report`)).text();}
 setTimeout(poll,1000)}
poll();
</script>"""
