# ADR 0001 — Architecture style

- Status: Accepted
- Date: 2026-11-16

## Context

Unjobless is a private single-owner app with four kinds of work: interactive web UI, domain CRUD/rules, long-running background collection/parsing, and AI calls. It must run on one ordinary VPS via Docker Compose, be easy to back up and migrate, and stay maintainable by one person. The dominant *hard* workload is collection, parsing, document processing and NLP — not UI.

## Options considered

| | A. Next.js full-stack (TS) + Python worker | B. TypeScript everywhere (Node API + Node workers) | **C. Python domain backend + worker, React/Vite PWA** |
|---|---|---|---|
| Domain logic language | Split TS/Python; schema defined twice (e.g. Drizzle + SQLAlchemy) | One (TS) | One (Python) |
| Crawling / parsing ecosystem | Python in worker only | Weaker: OCR, PDF/DOCX, readability, NLP less mature | Strong (trafilatura, selectolax, pypdf, python-docx, OCR bindings) |
| Background jobs | Two job systems or cross-language queue | BullMQ (needs Redis) | Procrastinate on Postgres (no Redis) |
| AI integration | Either | Either | Either; Pydantic schemas give strict structured-output validation |
| PWA | Good | Good | Good (Vite + vite-plugin-pwa) |
| Docker footprint | node server + python worker + db (+redis) | node + db + redis | api + worker (same image) + db + caddy |
| Ops simplicity | Medium | Medium | **High** — one image for api/worker, one DB to back up |
| Risk | Model drift between languages | Rebuilding mature Python tooling | SPA has no SSR — acceptable for a private, authenticated app |

## Decision

Choose **C**: one Python package (`unjobless`) providing the FastAPI HTTP API and the Procrastinate worker, plus a React + TypeScript SPA built with Vite and served statically by Caddy.

- SSR is not needed: every page sits behind private auth, there is no SEO requirement, and an SPA is a natural fit for an installable PWA.
- The API and worker share one codebase and image; they are separate *processes*, not services.
- Modules (`sources`, `ingestion`, `intelligence`, `profile`, `ai`, `applications`) are cohesive packages with explicit interfaces, so a later split stays possible.

## Consequences

- Two toolchains (uv + pnpm), but domain logic lives in one language.
- API contracts are shared via the generated OpenAPI schema; the frontend uses hand-written typed clients validated against it.
- No Redis: Postgres carries the queue, keeping backup/restore to one database plus one file volume.
