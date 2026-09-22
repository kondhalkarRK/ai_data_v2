# syntax=docker/dockerfile:1.7

# --- build stage -----------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip setuptools wheel \
 && pip install ".[analytics,rag]"

# --- runtime stage ---------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libpq is needed by psycopg; curl is used by the container healthcheck.
RUN apt-get update \
 && apt-get install --no-install-recommends -y libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1001 nql \
 && useradd --system --uid 1001 --gid nql --create-home nql

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=nql:nql app ./app
COPY --chown=nql:nql semantic ./semantic
COPY --chown=nql:nql migrations ./migrations
COPY --chown=nql:nql alembic.ini ./alembic.ini
COPY --chown=nql:nql pyproject.toml ./pyproject.toml

RUN mkdir -p /app/data/knowledge/automotive /app/data/knowledge/insurance /app/data/knowledge/_audit \
 && chown -R nql:nql /app/data

USER nql

EXPOSE 8000

# Render sets $PORT. Local docker still defaults to 8000.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c 'curl --fail --silent "http://127.0.0.1:${PORT:-8000}/health" || exit 1'

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
