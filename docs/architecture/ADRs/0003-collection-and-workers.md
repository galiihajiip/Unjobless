# ADR 0003 — Collection, workers and fetch safety

- Status: Accepted
- Date: 2026-11-16

## Decision

### Queue and scheduler
- **Procrastinate** (Postgres-backed) runs background tasks: source runs, URL import items, paste processing, AI extraction, lifecycle rechecks.
- Unjobless keeps its own **`source_runs` / `processing_jobs` tables** as the domain-level record (status, counters, errors, cursor). Procrastinate is the delivery mechanism; domain state never depends on Procrastinate internals, so the queue could be swapped.
- A periodic "scheduler tick" task (every minute) enqueues due source runs based on per-source `schedule_interval_seconds`, `next_run_at`, pause state and policy review.
- **No overlap:** a source run uses a queueing lock `source:<id>` and a DB-level partial unique index on `source_runs(source_id) WHERE status IN ('queued','running')`.
- Retries: exponential backoff with jitter, bounded attempts, then `failed` (dead-letter) state with the last error.
- Concurrency: global worker concurrency via worker settings; per-source caps via the source config enforced when claiming work.
- Stale-run recovery: runs `running` longer than `timeout × 2` without heartbeat are marked `failed` with reason `stale` and may be re-queued.

### Fetching
- One **`SafeFetcher`** is the only code path allowed to make outbound HTTP requests to user- or source-supplied URLs.
  - http/https only, default ports 80/443 only (allowlist configurable);
  - resolve DNS with dnspython, reject any non-global address (private, loopback, link-local, multicast, reserved, CGNAT, unspecified, IPv4-mapped IPv6, cloud metadata such as `169.254.169.254`, `fd00:ec2::254`);
  - connect to the **validated IP** (pinning) with SNI/Host set to the original hostname, which defeats DNS rebinding between check and connect;
  - manual redirect handling: each hop re-validated, max 5 hops;
  - connect/read/total timeouts; streamed body with byte cap (default 5 MB) and decompression cap; content-type allowlist;
  - no cookies, no auth headers forwarded, configurable honest User-Agent.
- **robots.txt** is honoured for crawler sources (cached per host); per-host rate limits and crawl-delay are enforced.
- **Browser automation is not included in v1.** If needed later it runs in a separate container on an isolated network with no route to `db`, and only for sources whose policy allows it.

### Parsing
- HTML: selectolax for DOM queries, trafilatura for main content, JSON-LD `JobPosting` extraction via a small parser.
- OCR/transcription (Block 16): pluggable; Tesseract inside the worker image when enabled, with CPU/time limits per task.

## Consequences

- Single worker process type; heavy media tasks can later be routed to a dedicated queue/worker replica without code changes.
- The SSRF guard is application-level; it is backed by Docker networking (db network internal, no published ports).
