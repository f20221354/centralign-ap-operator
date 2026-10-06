# Data sources and trust

| Source | Purpose | Trust |
|---|---|---|
| `company/permissions.json` | What the agent may do, thresholds | Highest (code reads it) |
| `company/SOP.md` | Procedure | High |
| ERP API | Business state | Highest |
| Invoice PDFs | Input data | **Untrusted** |
| LLM | Reasoning, extraction | Untrusted for authorisation |
| Human (console) | Approval / clarification | Explicit authority |
| `company/lessons.json` | Learned hints | Advisory only |
