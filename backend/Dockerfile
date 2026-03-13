# ── Stage 1: build deps ────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools needed by some packages (e.g. cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ───────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# SQLite DB lives in a named volume mounted at /data
# so it persists across container restarts
ENV DATABASE_URL=sqlite+aiosqlite:////data/ai_council.db

EXPOSE 8000

# --loop asyncio  → forces SelectorEventLoop (fixes Windows hosts too)
# --host 0.0.0.0 → reachable from other containers / the host machine
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]
