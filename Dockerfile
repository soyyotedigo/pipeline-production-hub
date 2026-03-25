# ── Stage 1: build / install deps ────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by some C-extension packages (e.g. asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

ARG INSTALL_EXTRAS=""

COPY pyproject.toml README.md ./
RUN if [ -n "$INSTALL_EXTRAS" ]; then \
        pip install --no-cache-dir --prefix=/install ".[${INSTALL_EXTRAS}]"; \
    else \
        pip install --no-cache-dir --prefix=/install .; \
    fi

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY backend/ ./backend/

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
