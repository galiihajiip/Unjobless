# Docker & Compose

Everything runs with Docker Engine + the Compose plugin. No application runtime is installed on the host.

## Services (`compose.yaml`)

| Service | Image | Purpose | Networks | Published ports |
|---|---|---|---|---|
| `db` | `postgres:17-alpine` | System of record + job queue | `data` (internal) | none |
| `migrate` | `unjobless-app` | One-shot `unjobless migrate` (Alembic) before app start | `data` | none |
| `api` | `unjobless-app` | FastAPI (`unjobless serve`) | `data`, `edge` | none |
| `worker` | `unjobless-app` | Procrastinate worker: collection, imports, OCR, AI, schedules, daily backup | `data`, `egress` | none |
| `proxy` | `unjobless-proxy` | Caddy: HTTPS, security headers, PWA files, `/api` reverse proxy | `edge` | 80, 443 (tcp+udp) |

- `data` is `internal: true`: the database has no internet route and the proxy cannot reach it.
- Only `proxy` publishes ports. The API and worker are never exposed directly.
- `api`/`worker` run as uid 10001 with a read-only root filesystem, `no-new-privileges` and `/tmp` as tmpfs. Writable state lives only on volumes.
- Startup order: `db` healthy → `migrate` completed → `api` healthy → `proxy`. The worker waits for `migrate`.
- Logs: json-file, 10 MB × 5 files per service.
- Memory limits: db 768 MB, api 768 MB, worker 1.5 GB (OCR). Recommended host: 2 vCPU / 4 GB RAM.

## Images

- `backend/Dockerfile`: multi-stage. A `uv` build stage with the frozen lockfile, then a `python:3.13-slim-trixie` runtime with `postgresql-client-17` (backups), `tesseract-ocr` (+`ind`, `eng`), `poppler-utils`, `fonts-dejavu-core` and `tini`. Non-root, with a healthcheck on `/api/health/live`. No secrets are baked in.
- `deploy/caddy/Dockerfile`: builds the PWA with pnpm (frozen lockfile) and copies `dist/` into `caddy:2-alpine` with `deploy/caddy/Caddyfile`.
- The images build on arm64 (tested on Apple Silicon). For an amd64 VPS, build on the server or with `docker buildx build --platform linux/amd64,linux/arm64`.

## Volumes

| Volume | Contents | Back up? |
|---|---|---|
| `pgdata` | PostgreSQL data | via `unjobless backup` (pg_dump) |
| `files` | CVs, raw blobs, media, exports | via `unjobless backup` (tarball) |
| `backups` | Backup directories | copy off-server |
| `caddy_data`, `caddy_config` | TLS certificates, ACME state | optional |

Data survives `docker compose down` and container re-creation. Only `docker compose down -v` deletes volumes.

## Run locally

```bash
cp .env.example .env          # fill in secrets (see below)
docker compose up -d --build
docker compose ps
open https://localhost        # Caddy's local CA; accept the certificate or trust it
```

Generate secrets with `docker compose run --rm --no-deps api unjobless gen-key` (once for `UNJOBLESS_MASTER_KEY`, once for `UNJOBLESS_SESSION_SECRET`, once for `POSTGRES_PASSWORD`).

To use other ports locally, set `HTTP_PORT=8080 HTTPS_PORT=8443` in `.env`.

## First-time setup

Open the site. The setup page asks for a **setup token**:
- set `UNJOBLESS_BOOTSTRAP_TOKEN` in `.env`, or
- read the generated one with `docker compose exec api cat /data/files/bootstrap-token.txt`.

The token file is deleted after the owner account is created. Bootstrap works only once.

## Useful commands

```bash
docker compose logs -f worker                     # collection / processing logs
docker compose exec api unjobless backup          # verified backup into the backups volume
docker compose exec api unjobless integrity-check # file references + master-key check
docker compose exec api unjobless eval-signals    # signal-engine evaluation report
docker compose pull db && docker compose up -d --build   # update
```

## Verified

On 2026-11-16 a fresh `docker compose up -d --build` with empty volumes reached all-healthy. `deploy/scripts/smoke_test.py` then passed end to end, including a live documented Greenhouse board that the worker collected: 254 jobs, all processed to verified vacancies through the queue.
