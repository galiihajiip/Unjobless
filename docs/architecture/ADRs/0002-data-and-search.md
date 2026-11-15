# ADR 0002 — Data storage and search

- Status: Accepted
- Date: 2026-11-16

## Decision

1. **PostgreSQL 17** is the system of record and the job queue store. Self-hosted in Compose; no managed database (Supabase etc.) is required.
2. **SQLAlchemy 2 + Alembic** own the schema. Every change is a versioned migration; `alembic upgrade head` runs from an empty database.
3. **Typed columns for anything filtered, sorted or joined** (title, company, status, classification, work arrangement, dates, compensation numbers, scores). **JSONB only** for raw connector payloads, AI raw output, flexible extracted extras, and evidence span metadata.
4. **Search:** PostgreSQL full-text search with the `simple` text-search configuration plus the `unaccent` extension, because Postgres ships no Indonesian stemmer. A generated `tsvector` column on vacancies/signals with a GIN index; `pg_trgm` for fuzzy company/title matching and deduplication candidates.
5. **Vectors deferred.** `pgvector` is not installed until an evaluation shows semantic matching beats lexical/skill-taxonomy matching on the evaluation set. The schema leaves room for an embeddings table.
6. **Files** (original CVs, raw HTML blobs over the inline threshold, media, exports) live on a named Docker volume behind a small `FileStore` interface (local filesystem implementation; an S3-compatible adapter can be added later). Files are content-addressed (sha256) and never served without auth.
7. **Timestamps** are `timestamptz` in UTC. Dates whose timezone is unknown are stored with an explicit `*_tz_uncertain` flag or as `date`.

## Alternatives rejected

- **Elasticsearch/OpenSearch/Meilisearch:** another stateful service to run and back up; Postgres FTS is enough at personal scale (tens of thousands of records).
- **Document DB:** relational constraints (max-two comparison, provenance links, unique source refs) are core requirements.

## Consequences

Backup = `pg_dump` + file volume tarball + the master key held separately. Search quality for Indonesian relies on the `simple` config and synonym handling in the application layer (e.g. "loker" ↔ "lowongan").
