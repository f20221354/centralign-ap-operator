# Decisions

001 **API for reads, browser for writes.** Realistic for legacy ERPs, demonstrates computer use, and lets the
verifier check through a different channel from the one the agent wrote through.

002 **No vector DB.** The SOP fits in the prompt. Add retrieval when the knowledge base stops fitting.

003 **Independent verifier.** The executor never declares its own success.

004 **PDF text layer + LLM extraction.** Works with every provider; scanned PDFs are a documented limit. Policy re-uses the runtime's extraction, not the model's arguments.

008 **One OpenAI-compatible LLM path with a failover chain** (Groq → Gemini → Ollama) instead of a vendor SDK: free tiers have small quotas, so running out must degrade, not stop. History is plain dicts so a different provider can continue a run. JSON output is prompt-only and validated in code (no provider-specific JSON modes).

009 **Runtime nudges a model that stops early**, based on the real inbox state (max 3), because small models narrate instead of calling tools. Finishing is never taken on the model's word: the verifier decides.

005 **One process, threads, sqlite** for run state. Swap for a queue + Postgres when there is more than one
operator.

006 **Fewer files than the original plan** (no separate classifier/recovery/approval modules): each is a
function in runtime/tools, which keeps the loop readable in one place.

007 **Crash recovery by reconciliation, not conversation replay.** ERP + folders are the source of truth;
the idempotency key makes re-execution safe.
