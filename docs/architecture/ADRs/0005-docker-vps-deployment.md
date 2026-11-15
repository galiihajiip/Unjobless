# ADR 0005 — Docker Compose VPS deployment

- Status: Accepted
- Date: 2026-11-16

## Decision

- **Compose services**: `proxy` (Caddy, serves PWA + reverse proxy), `api`, `worker`, `migrate` (one-shot `alembic upgrade head`), `db` (postgres:17). `api` and `worker` use the same image.
- **Images**: multi-stage; Python runtime on `python:3.13-slim` with a non-root user; the PWA is built in a `node` stage and copied into the Caddy image. Built for `linux/amd64` and `linux/arm64` (dev Mac is arm64, typical VPS is amd64).
- **Volumes**: `pgdata`, `files`, `caddy_data`, `caddy_config`, `backups`.
- **Networks**: `edge` (proxy, api) and `internal` (api, worker, db) with db unreachable from the proxy. Only `proxy` publishes 80/443. Postgres is never published in production.
- **Config**: `.env` on the server (from `.env.example`); `UNJOBLESS_MASTER_KEY`, `POSTGRES_PASSWORD`, `UNJOBLESS_SESSION_SECRET` required at runtime, never baked into images.
- **Health**: `/api/health/live` and `/api/health/ready` (DB check); Compose healthchecks gate startup order (`db` healthy → `migrate` completed → `api`/`worker`).
- **Dev**: `compose.dev.yaml` runs only Postgres on `127.0.0.1:5433` for local development; app processes run natively with hot reload.
- **Sizing**: target ≥ 2 vCPU / 4 GB RAM. Without OCR/browser, the stack runs in ~1.5 GB.
- **Reverse proxy**: Caddy (automatic HTTPS via ACME, minimal config) rather than Traefik (label-driven, more moving parts) or nginx + certbot.

## Migration

New server: install Docker → copy repo + `.env` (+ master key) → `docker compose up -d` → restore `pg_dump` and file volume via `deploy/scripts/restore.sh` → migrations run automatically → DNS cutover. Proven in Block 40.
