# The agent + Operator Console. Needs a real Chromium and long-running processes, so it can't be a Vercel function.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium
COPY agent agent
COPY company company
CMD ["sh", "-c", "uvicorn agent.console:app --host 0.0.0.0 --port ${PORT:-8000}"]
