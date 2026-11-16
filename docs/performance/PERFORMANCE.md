# Performance & resource limits

## Measured (2026-11-16, Apple Silicon, Postgres 17 in Docker, through FastAPI)

`python -m unjobless.evaluation.perf <scratch-db-url> 20000` seeds 20,000 synthetic vacancies (400 companies, locations, skills and match analyses), then times each request 7×:

| Request | p50 | max |
|---|---|---|
| Feed, newest, 25 items | 56 ms | 216 ms (cold) |
| Full-text search `data analyst jakarta`, relevance | 23 ms | 29 ms |
| City + employment type + arrangement filters | 36 ms | 49 ms |
| Two skill filters, best-fit sort | 48 ms | 52 ms |
| Deadline sort + min confidence | 50 ms | 82 ms |
| Facets | 68 ms | 88 ms |
| Overview | 43 ms | 59 ms |
| Page 21 via keyset cursor | 60 ms | 71 ms |

Personal scale is expected to stay below 20k active vacancies, so **no extra caching or services were added**: these numbers need no optimisation. Keyset pagination keeps deep pages as fast as the first. The live Greenhouse run (254 jobs) was collected and fully processed by one worker in about a minute.

## Configurable limits

| Limit | Setting | Default |
|---|---|---|
| URLs per import batch | `UNJOBLESS_MAX_URLS_PER_BATCH` | 50 |
| Response bytes per fetch (after decompression) | `UNJOBLESS_FETCH_MAX_BYTES` | 5 MB |
| Upload size | `UNJOBLESS_MAX_UPLOAD_BYTES` (+ Caddy 12 MB) | 10 MB |
| Pasted text | `UNJOBLESS_MAX_PASTE_CHARS` | 200,000 |
| Fetch timeouts | `UNJOBLESS_FETCH_CONNECT/READ/TOTAL_TIMEOUT` | 5 / 15 / 30 s |
| Redirects | `UNJOBLESS_FETCH_MAX_REDIRECTS` | 5 |
| Pages per crawl run | source config `max_pages` | 50 (max 500) |
| Crawl depth | listing → detail only (depth 1) | fixed |
| Items per run | `CollectContext.max_items` | 500 |
| Run timeout | `source_runs.timeout_seconds` | 600 s |
| Per-source rate | source `rate_limit_per_minute` (+ robots crawl-delay) | 10–30/min |
| Per-source concurrency | one active run per source (DB-enforced) | 1 |
| Global worker concurrency | `UNJOBLESS_GLOBAL_WORKER_CONCURRENCY` | 4 |
| OCR | 90 s wall, 60 s CPU, 1 GB address space per subprocess; ≤ 10 PDF pages | fixed |
| PDF text pages | 30 | fixed |
| Browser automation | not included | — |
| AI output tokens | per task (`ai/tasks.py`), 2k–16k | per task |
| AI cost | daily budget (AI Studio) | none |
| Raw text inline | 1 M chars (rest in file store), raw cap 10 MB | fixed |
| Container memory | db 768 MB, api 768 MB, worker 1.5 GB | compose |

Runaway work is bounded by run timeouts, stale-run recovery, item caps, subprocess limits and per-task queueing locks. Failed work is retried safely because every step is idempotent (content hashes, DB uniqueness, queueing locks).

## PWA asset size

The production build precaches 54 entries (~0.8 MB, mostly Inter font subsets). Routes are code-split.
