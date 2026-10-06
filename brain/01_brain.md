# CentrAlign in one page

**What:** an AI employee that turns a vague company request into verified, completed work.
**Prototype scope:** accounts payable: "Process this week's vendor invoices".

```
LLM      = reasoning (any OpenAI-compatible model: Groq, Gemini, Ollama; understands, plans, picks tools, adapts)
Runtime  = control (agent/runtime.py)
Tools    = execution (browser, ERP read API, files)
Policy   = authority (agent/policy.py)
Verifier = truth (agent/verifier.py)
Events   = memory of execution (agent/store.py)
```

Loop: Goal → Understand (SOP + lessons) → Propose → Policy → Execute or ask human → Observe → Classify →
Retry / Re-auth / Adapt / Replan / Reconcile → … → Verify → Report → Learn.
