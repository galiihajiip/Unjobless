# Testing, evaluation & quality gates

## Test suites

| Level | Where | What it covers |
|---|---|---|
| Unit | `backend/tests/test_signals.py`, `test_extraction.py`, `test_ai.py`, `test_health.py` | Signal rules, ID/EN parsing (salary, dates, skills), strict AI schemas, gateway retries/cooldowns/budget/fallback, redaction |
| Database / migrations | `test_schema.py` | Migrate from empty; constraints (single owner, enabled-requires-policy, one active run, comparison max two, salary order, enum checks); FTS |
| Security | `test_auth.py`, `test_safe_fetch.py`, `test_ai.py` (API) | Auth boundaries for every route, CSRF, throttling, session revocation, SSRF (private IPs, metadata, rebinding, redirects, ports, schemes), size/decompression caps, key never returned/encrypted at rest |
| Queue / worker | `test_runner.py` | Success, retry with backoff, rate-limit retry-after, unavailable, duplicate enqueue, double execution, pause, timeout, cancellation, worker-restart stale recovery, scheduler idempotency, item-level failure |
| Connector contracts | `test_connectors.py`, `test_crawler.py` | Greenhouse/Lever/Ashby recorded fixtures; crawler with local fixture HTML: domain/path scope, JSON-LD, robots disallow, CAPTCHA wall, change detection |
| Pipeline integration | `test_pipeline.py`, `test_imports.py`, `test_profile_flow.py`, `test_feed.py` | ATS → verified vacancies with provenance; lifecycle rules; dedup (merge, undo, no false merges); URL/paste import + review; CV → profile → matching → compare → tailoring → export → tracker; feed filters/pagination |
| UI | `apps/web/src/**/*.test.tsx` | Auth gate, navigation, every route renders with mocked data, accessible button names |
| End-to-end / Docker | `deploy/scripts/smoke_test.py` | Full stack over HTTPS incl. worker processing and a live documented ATS board |
| Backup/restore | `smoke_test.py --phase verify` after restore | See `docs/deployment/MIGRATION.md` |
| Performance | `python -m unjobless.evaluation.perf` | See `docs/performance/PERFORMANCE.md` |

Run everything locally: `make dev-db && make check`. CI: `.github/workflows/ci.yml`.

Latest local run (2026-11-16): **backend all tests passing, 73% line coverage** (uncovered code is mostly CLI/worker entry points and backup, which the Docker smoke test exercises), mypy 0 issues, frontend 20/20.

## Evaluation datasets (synthetic, privacy-safe)

| Dataset | Purpose |
|---|---|
| `tests/fixtures/eval/signals*.jsonl` | Opportunity classification: direct vacancy, internship poster, informal referral, future-hiring rumour, job-search question, employer review, negative interview experience, unrelated "internship", expired opening, recruitment poster with missing details, injection attempt |
| Inline fixtures in `test_extraction.py` | Field extraction (ID/EN, incomplete salary/location/deadline) |
| `test_pipeline.py` | Duplicate across sources; same-role-different-country non-duplicate |
| `test_profile_flow.py` | CV fact preservation, claim checks, comparison reproducibility |
| `tests/fixtures/ats/*.json` | Trimmed real public ATS responses (no personal data) |

Signal results: [`docs/evaluation/SIGNALS_EVAL.md`](../evaluation/SIGNALS_EVAL.md).

## Release gates (enforced by CI)

1. Lint + format + mypy clean.
2. No migration drift; upgrade → downgrade → upgrade succeeds.
3. All tests pass, including:
   - opportunity precision **= 1.0** on every evaluation set (no false opportunities);
   - dev-set accuracy ≥ 0.95 (regression guard);
   - every private route rejects anonymous requests;
   - SSRF suite;
   - comparison rejects ≠ 2 vacancies at DB, service and API.
4. Frontend lint, types, tests, build.
5. Docker images build.

## Not yet evaluated

- Live-model AI accuracy (no API key in this environment).
- Entity-resolution accuracy on real company names at scale.
- OCR quality on real posters (Tesseract present only in the Docker image).
