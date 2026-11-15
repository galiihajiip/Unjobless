# syntax=docker/dockerfile:1.7
# Unjobless API + worker image (same image, different command).

FROM python:3.13-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.13-slim-trixie AS runtime
# pg_dump/pg_restore 17 (backups), tesseract + poppler (OCR, scanned PDFs), DejaVu fonts (PDF export).
# Package lists are kept out of the final layer via a cache mount.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 tesseract-ocr tesseract-ocr-eng tesseract-ocr-ind poppler-utils fonts-dejavu-core tini \
 && groupadd --system --gid 10001 unjobless \
 && useradd --system --uid 10001 --gid unjobless --home /app --shell /usr/sbin/nologin unjobless \
 && mkdir -p /data/files /data/backups && chown -R unjobless:unjobless /data
WORKDIR /app
COPY --from=build --chown=unjobless:unjobless /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    UNJOBLESS_FILES_DIR=/data/files UNJOBLESS_BACKUP_DIR=/data/backups
USER unjobless
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["unjobless", "serve", "--host", "0.0.0.0", "--port", "8000"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=4).status == 200 else 1)"]
