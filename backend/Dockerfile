# ── TALVEX Backend — Python FastAPI (Phase 8 — Hardened) ───
FROM python:3.12-slim AS base

WORKDIR /app

# System deps for pdfminer, pytesseract, Typst, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (before adding source — better caching)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/
COPY db/ ./db/

# Install Typst (for PDF compilation)
RUN curl -sSL https://github.com/typst/typst/releases/latest/download/typst-x86_64-unknown-linux-musl.tar.xz \
    | tar -xJ -C /usr/local/bin --strip-components=1 typst-x86_64-unknown-linux-musl/typst

# ── Non-root user (security hardening — Phase 8) ───────────
RUN groupadd -r appuser && useradd -m -r -g appuser appuser

# Create writable directories for logs and temp files
RUN mkdir -p /app/logs /app/tmp && \
    chown -R appuser:appuser /app/logs /app/tmp

# Switch to non-root user
USER appuser

EXPOSE 8000

# Default: run the FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
