# Unjobless

**Discover broadly. Understand deeply. Apply deliberately.**

Unjobless is a private, self-hosted career discovery and application workspace for one owner. It collects opportunities from sources you have reviewed and enabled, and from URLs and posts you import. It keeps the original evidence, extracts rich structured data in Indonesian and English, and separates real vacancies from informal leads and from discussion. It matches opportunities to your confirmed CV, compares two vacancies side by side and helps you prepare truthful, evidence-backed applications. It never applies on your behalf.

## Capabilities

- **Sources:** documented public ATS boards (Greenhouse, Lever, Ashby) and a robots.txt-compliant career-page crawler (JSON-LD `JobPosting`, sitemaps, RSS). Sources stay disabled until you record a terms review; an exclusion list blocks domains.
- **Import Center:** URL batches (SSRF-safe fetching, per-item status, paste fallback), pasted posts stored exactly as pasted, poster/PDF/caption uploads with OCR, and a **“Send to Unjobless” browser clipper** for sites that block bots (Glints, LinkedIn, JobStreet…): it sends only the page you are viewing yourself.
- **Evidence first:** immutable raw snapshots with content hashes and versions. Every extracted field has an origin (explicit / inferred / yours), a confidence and a verbatim excerpt.
- **Opportunity Signals:** a bilingual rule engine (loker, magang, refer, oprec…) separates `DIRECT_VACANCY` from leads, referrals, campaigns, reviews, discussions and noise. Confidence never "verifies" anything.
- **Lifecycle:** first/last seen, checked and verified dates; explicit deadlines expire vacancies; a failed fetch is never treated as "closed".
- **Deduplication** across sources (keeps every source reference, with a review queue and undo) and company resolution.
- **Career profile:** CV (PDF/DOCX) → draft → your review → confirmed, versioned master profile, plus preferences.
- **Matching:** separate profile-fit, preference-fit and data-confidence scores with evidence. Unknown is never zero.
- **Compare** exactly two vacancies: criterion winners, trade-offs and editable weights.
- **Tailoring:** claim-by-claim CV suggestions tied to profile facts; new numbers or skills are flagged. Cover letters; PDF/DOCX export (ATS Classic and Modern Professional templates).
- **Applications tracker** with history; apply links open the original site.
- **Career Intelligence:** topics, sampled public sentiment and weekly trends, with sample sizes.
- **AI Studio (optional):** Claude via the official Anthropic SDK, or another OpenAI-compatible provider. Keys are encrypted, masked and rotatable; budgets, task routing and usage history included. Everything works without AI.
- **PWA:** installable on iOS, Android and desktop; offline app shell; private data is never cached.

## Architecture

A Python modular monolith (FastAPI API and a Procrastinate worker in one image), PostgreSQL 17 as the system of record **and** the job queue, a React + Vite PWA, and Caddy for TLS. No Redis and no microservices. See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) and the [ADRs](docs/architecture/ADRs/).

```
apps/web/      React + TypeScript PWA
backend/       Python package `unjobless` (API, worker, CLI), Alembic migrations, tests
deploy/        Caddy image + Caddyfile, scripts (restore, smoke test, icons)
docs/          product, architecture, domain, design, deployment, security, evaluation
compose.yaml   production stack     compose.dev.yaml  local Postgres for development
```

## Prerequisites

- **Run it:** Docker Engine + Compose plugin.
- **Develop:** Python 3.13 + [uv](https://docs.astral.sh/uv/) 0.13, Node 26 + pnpm 11, Docker (for Postgres).

## Quick start (Docker)

```bash
cp .env.example .env
docker compose run --rm --no-deps api unjobless gen-key   # run three times, paste into .env:
#   UNJOBLESS_MASTER_KEY, UNJOBLESS_SESSION_SECRET, POSTGRES_PASSWORD
docker compose up -d --build
```

Open `https://localhost` (or your domain), enter the setup token (set `UNJOBLESS_BOOTSTRAP_TOKEN`, or read `docker compose exec api cat /data/files/bootstrap-token.txt`) and create your owner account.

**Back up `UNJOBLESS_MASTER_KEY` in a password manager.** Without it, restored backups lose the stored AI keys (everything else restores).

VPS with a domain and automatic HTTPS: [docs/deployment/VPS.md](docs/deployment/VPS.md). Container details: [docs/deployment/DOCKER.md](docs/deployment/DOCKER.md).

## Local development

```bash
make dev-db                                  # Postgres 17 on 127.0.0.1:5433 (+ test database)
cd backend && uv sync && uv run unjobless migrate && uv run unjobless seed   # synthetic [FIXTURE] data
make dev-api                                 # http://127.0.0.1:8000  (OpenAPI: /api/docs)
make dev-worker                              # background jobs
pnpm install && make dev-web                 # http://localhost:5173  (proxies /api)
```

In development no setup token is needed. Configuration is read from `UNJOBLESS_*` environment variables (see `backend/src/unjobless/core/config.py` and `.env.example`). Production refuses to start without strong secrets.

### Migrations

```bash
cd backend
uv run alembic revision --autogenerate -m "describe change"   # then review the file
uv run unjobless migrate                                       # = alembic upgrade head
uv run alembic check                                           # fails on model/migration drift
```

### Tests & checks

```bash
make check          # ruff + mypy + pytest (backend) and eslint + tsc + vitest (web)
cd backend && uv run unjobless eval-signals   # opportunity-signal evaluation report
```

Details: [docs/quality/TESTING.md](docs/quality/TESTING.md). CI: `.github/workflows/ci.yml`.

## Adding a source connector

1. Create `backend/src/unjobless/sources/connectors/<name>.py` with a `Connector` subclass declaring a `ConnectorInfo` (type, category, collection method, documentation and terms URLs, Pydantic `config_model`, default schedule and rate, capabilities).
2. Implement `collect(ctx)` to yield `CollectedItem`s. Use `ctx.fetcher` for documented APIs, or `ctx.polite_get` (robots.txt + rate limits) for pages. Raise `SourceUnavailable` for login/CAPTCHA/403 (never bypass) and `SourceRateLimited` for quotas. Put explicit API fields in `structured=[{...}]` with a `provenance` label.
3. Decorate with `@register` and import the module in `sources/connectors/__init__.py`.
4. Add fixture-based contract tests (see `tests/test_connectors.py`).

The scheduler, raw store, processing pipeline and UI need no changes.

## Adding an AI provider

Implement a class with `complete_json(model, system, user, schema, max_tokens, effort, timeout) -> ProviderResult` in `backend/src/unjobless/ai/providers.py`. Map provider errors to `ProviderRateLimited` / `ProviderUnavailable` / `ProviderAuthError` / `ProviderBadRequest` / `ProviderRefused`, then register it in `build_adapter`. Tasks, prompts and schemas live in `ai/tasks.py` and `ai/task_schemas.py` (versioned).

## Using it

- **Import:** Import Center › URLs (one per line), Paste content, or Poster / PDF. Review each item, then *save as vacancy* (you confirm it is real), *save as lead*, *merge* or *reject*.
- **PWA:** Settings › Install help.
- **Backups:** automatic daily backups in Docker, plus Settings › Backups. Restore with `deploy/scripts/restore.sh` ([MIGRATION.md](docs/deployment/MIGRATION.md)).

## Troubleshooting

| Symptom | Check |
|---|---|
| Setup page asks for a token | `UNJOBLESS_BOOTSTRAP_TOKEN` in `.env` or `docker compose exec api cat /data/files/bootstrap-token.txt` |
| API refuses to start in production | `UNJOBLESS_MASTER_KEY` / `UNJOBLESS_SESSION_SECRET` missing or shorter than 32 bytes |
| Imports stay "Queued" | `docker compose logs worker`; the worker must be running. Queued work is re-delivered every minute. |
| URL import "unavailable" | The site needs login, blocks bots or disallows it in robots.txt. Use Paste content. |
| Source health "Rate limited" | It retries automatically after the source's `Retry-After`; lower its schedule. |
| AI tasks skipped | AI Studio: provider enabled with a key, not cooling down, budget not exhausted |
| No HTTPS certificate | DNS must point at the server and ports 80/443 must be open: `docker compose logs proxy` |

## Security & collection policy

Private single-owner instance: no public sign-up. Collection uses only documented APIs and permitted public pages, respects robots.txt, rate limits and terms, and never bypasses logins, CAPTCHAs, paywalls or private groups. Scraped content is treated as untrusted data, never as instructions. See [docs/security/SECURITY_REVIEW.md](docs/security/SECURITY_REVIEW.md), [THREAT_MODEL.md](docs/security/THREAT_MODEL.md) and [KNOWN_LIMITATIONS.md](docs/release/KNOWN_LIMITATIONS.md).

Operator tasks (source health, key rotation, reviewing leads, corrections, restores): [docs/operations/OPERATOR_HANDBOOK.md](docs/operations/OPERATOR_HANDBOOK.md).
