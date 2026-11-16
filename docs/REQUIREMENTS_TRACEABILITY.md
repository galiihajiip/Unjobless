# Unjobless — Requirements Traceability Matrix

Maps every major requirement in `docs/UNJOBLESS_BUILD_PLAYBOOK.md` to the prompt block(s) that implement it and the test that proves it. Block numbers refer to the playbook's prompt blocks (00–43). Status is updated as blocks complete.

**Legend** — *Impl*: primary implementing block(s); *Also*: supporting blocks; *Test*: verification type (U unit, I integration, C contract, E2E end-to-end, S security, M manual/visual, D docs review, EV evaluation dataset).

Status values: `planned`, `in-progress`, `done`, `partial`, `deferred`.

**Status as of 2026-11-16:** all blocks 00–43 implemented. Exceptions are marked `partial` below, with the reason in [KNOWN_LIMITATIONS](release/KNOWN_LIMITATIONS.md).

---

## 1. Product workflows (playbook §4)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| WF-A1 | First-run owner setup, one-time bootstrap | 07 | 05 | S: bootstrap cannot repeat; E2E setup | done |
| WF-A2 | Career preferences captured | 24 | 35 | I: preferences persist; U: validation | done |
| WF-A3 | Upload CV (PDF/DOCX), extract, propose profile | 23 | 16, 27 | I: upload→extraction; fixture CVs (synthetic) | done |
| WF-A4 | Review/correct/confirm profile; versioned original + extraction | 23 | 06 | I: versioning; original unchanged | done |
| WF-B1 | Scheduled per-source collection with quotas | 11 | 08, 10 | I: schedule, no overlap, quota | done |
| WF-B2 | Raw docs preserved with attribution/timestamps | 09 | — | U: hashing/versioning | done |
| WF-B3 | Classify, extract, dedupe, freshness, matching eligibility | 17, 19, 20, 21 | 24 | EV + U state transitions | done |
| WF-C1 | Batch URL import, SSRF-safe, per-item status | 14 | 10 | S: SSRF suite; I: partial batch failure | done |
| WF-C2 | Blocked/login pages → paste fallback | 14 | 15 | E2E: fallback path | done |
| WF-C3 | Review screen before save/merge | 33 | 14, 20 | E2E: confirm/merge/reject | done |
| WF-D1 | Paste import preserving exact text + metadata | 15 | 09 | U: exact text + hash preserved | done |
| WF-D2 | Saved as vacancy or unverified lead | 15, 33 | 17 | I: lead never auto-promoted | done |
| WF-E1 | Feed separates vacancies from leads | 22 | 17 | E2E: badges/categories | done |
| WF-E2 | Feed filters (role…match score) | 22 | 24 | I: filter combinations; stable pagination | done |
| WF-E3 | First seen / last checked / last verified / freshness shown | 22 | 21 | E2E | done |
| WF-E4 | Save/dismiss/interesting/applied/archive/report | 22, 31 | — | I | done |
| WF-E5 | Original application CTA when URL valid | 22, 31 | — | U: URL validation | done |
| WF-F1 | Compare exactly two; reject third (UI **and** API) | 25 | — | S/I: 0,1,3, duplicate IDs rejected | done |
| WF-F2 | Criterion winner A/B/Tie/Unknown with evidence; editable weights | 25 | 24 | U: reproducible math, missing ≠ zero | done |
| WF-G1 | Evidence-grounded tailored CV, per-change accept/reject | 29 | 27 | U: every claim evidence-linked | done |
| WF-G2 | PDF/DOCX export with templates; master never overwritten | 30 | 29 | I: files open; master hash unchanged | done |
| WF-G3 | Link back to original application page | 31 | — | E2E | done |

## 2. Design & UX (playbook §5–7)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| UX-1 | Design tokens (palette, gradient, radius, shadow) | 04 | 41 | M: visual review; token doc | done |
| UX-2 | Original branding; no reference brand/mascot/medical copy | 04 | 32, 41 | M/D | done |
| UX-3 | Responsive: mobile bottom nav, tablet, desktop sidebar | 04, 05 | 41 | E2E at 360/768/1366/1440 widths | done |
| UX-4 | Accessibility: WCAG AA contrast, keyboard, labels, reduced motion | 04 | 41 | Automated a11y checks + M | done |
| UX-5 | Loading / empty / error states on every page | 05 | 22, 41 | M + component tests | done |
| UX-6 | No dead buttons; future modules disabled with explanation | 05 | 41 | E2E link/button crawl | done |
| UX-7 | Brand voice, no exaggerated claims | 05 | 43 | D: copy review | done |
| UX-8 | Score visuals never colour-only | 22, 25 | 41 | M + a11y | done |

## 3. Navigation (playbook §8)

| ID | Requirement | Impl | Test | Status |
|---|---|---|---|---|
| NAV-1 | 11 sections: Overview, Discover, Signals, Compare, Profile, Applications, Import Center, Sources, Career Intelligence, AI Studio, Settings | 05 | E2E route navigation | done |
| NAV-2 | Active route state; mobile nav | 05 | E2E | done |

## 4. Classification, status, extraction (playbook §9–12)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| CLS-1 | Categories `DIRECT_VACANCY` … `IRRELEVANT`, primary + secondary | 02, 17 | 06 | EV confusion matrix | done |
| CLS-2 | "Internship" mention ≠ vacancy; rumour ≠ verified | 17 | 36 | EV critical examples | done |
| CLS-3 | Indonesian + English incl. slang (magang, loker, lowker…) | 17 | 19 | EV false-positive cases | done |
| STS-1 | Verification statuses (`NEW_UNREVIEWED` … `SOURCE_UNAVAILABLE`) | 02, 21 | 06 | U state machine | done |
| STS-2 | Exposed: classification, status, confidence, evidence, timestamps, deadline, freshness, why recommended, unknowns | 22 | 21, 24 | E2E | done |
| EXT-1 | Rich field model (identity, details, requirements, compensation, context) | 02, 06, 19 | — | Golden fixtures (ID/EN) | done |
| EXT-2 | Field-level evidence, confidence, explicit/inferred/missing markers | 19 | 27 | U schema validation | done |
| EXT-3 | Missing → null; no inferred salary/deadline/eligibility | 19 | 36 | EV: no-fabrication checks | done |
| SIG-1 | Opportunity signal detection separate from sentiment | 17, 18 | 02 | U: sentiment never changes vacancy state | done |
| SIG-2 | Sentiment polarity + target + evidence + sarcasm uncertainty | 18 | 27 | EV | done (rule-based; AI path not live-evaluated) |
| SIG-3 | Topic clustering | 18 | — | EV | done |
| SIG-4 | Trends from observed counts; small samples labelled | 18, 34 | — | U: reproducible aggregates | done |

## 5. Architecture & deployment (playbook §13)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| ARC-1 | Compare ≥2 architectures; ADRs in `docs/architecture/` | 01 | — | D | done |
| ARC-2 | No premature microservices | 01 | 37 | D | done |
| ARC-3 | Self-hosted Postgres as system of record; no mandatory managed services | 01, 06 | 38 | D + Docker smoke | done |
| ARC-4 | `docker compose up -d --build` runs everything | 38 | 39 | Docker smoke test | done |
| ARC-5 | Engineering baseline: lockfiles, lint, typecheck, tests, env validation, logging | 03 | 36 | CI | done |

## 6. Collection, safety, reliability (playbook §14–18)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| SRC-1 | Connector contract with declared capabilities | 08 | — | C: mock connector added without core changes | done |
| SRC-2 | Data-driven registry; enable/disable/pause; denylist | 08 | 28 | I: disabled source cannot collect | done |
| SRC-3 | Unclear permission → disabled by default | 08, 13 | — | U | done |
| SRC-4 | Respect robots, ToS, quotas; no login/CAPTCHA/paywall bypass | 10, 13 | 42 | S + D | done |
| SRC-5 | Documented job API/ATS connectors | 12 | — | C with recorded fixtures | done |
| SRC-6 | Permitted career-page crawler (JSON-LD, sitemaps, RSS, ETag) | 13 | — | I with local fixture HTML | done |
| SRC-7 | Multimodal OCR/transcription with provenance | 16 | — | I with sample posters | partial — OCR/PDF/captions implemented (Tesseract in Docker image); speech transcription not bundled |
| SSRF-1 | http/https only; block private/loopback/link-local/metadata/reserved | 10 | 14 | S | done |
| SSRF-2 | DNS re-check, rebinding defence, redirect revalidation | 10 | — | S: redirect-to-private-IP | done |
| SSRF-3 | Timeouts, size/decompression caps, content-type checks, port policy | 10 | 37 | S/U | done |
| SSRF-4 | Browser workers isolated from internal services | 10, 38 | 42 | S: network policy test | done |
| ORC-1 | Persistent scheduler/queue; retries w/ backoff+jitter; DLQ | 11 | — | I | done |
| ORC-2 | Per-source + global concurrency; no overlapping runs; cancellation | 11 | 37 | I | done |
| ORC-3 | Idempotency, cursors/checkpoints, graceful shutdown, stale-lock recovery | 11 | — | I: worker restart | done |
| RAW-1 | Raw stored separately; hashes; versions on change | 09 | — | U | done |
| RAW-2 | No secrets/cookies stored; size limits; retention | 09 | 35 | U | done |
| DUP-1 | Multi-signal deduplication; canonical + multiple source refs | 20 | — | I: same vacancy from 2 sources → 1 record | done |
| DUP-2 | No false merges (different location/level) | 20 | 36 | EV dedup precision | done |
| DUP-3 | Company aliases, manual correction, merge undo/audit | 20 | — | I | done |
| LIF-1 | Track first/last seen, checked, verified, published, deadline, closed, reason | 21 | 06 | U | done |
| LIF-2 | Failed fetch ≠ closed; explicit past deadline → expired | 21 | — | U deterministic transitions | done |

## 7. AI provider gateway (playbook §19)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| AI-1 | Provider/model registry, adapters, task routing | 26 | 27 | U with mocked providers | done |
| AI-2 | Structured output validation; bounded retries | 26, 27 | — | U: malformed output rejected | done |
| AI-3 | Usage/cost tracking, budgets, cooldown after rate limit | 26 | 37 | U | done |
| AI-4 | Keys encrypted at rest with env master key; masked; never returned | 26 | 35, 42 | S: API never returns key | done |
| AI-5 | No key rotation to evade quotas | 26 | — | D + U (cooldown honoured) | done |
| AI-6 | Versioned prompts and schemas; metadata stored with results | 27 | — | U | done |
| AI-7 | Minimise personal data sent; redact contact details for matching | 27 | 23 | U | done |
| AI-8 | Scraped content treated as data (prompt-injection defence) | 27 | 42 | S: injection fixtures | done |

## 8. Profile, matching, comparison, tailoring (playbook §20–23)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| PRF-1 | Validate type/MIME/size; private storage | 23 | 07 | S/U | done |
| PRF-2 | Profile sections; versions; fact verified/corrected flags | 23 | 06 | I | done |
| PRF-3 | Never invent metrics/titles/dates | 23 | 36 | EV: CV fact preservation | done |
| MAT-1 | Layered matching; deterministic scores | 24 | — | U: score calc documented | done |
| MAT-2 | Separate `candidate_fit`, `preference_fit`, `data_confidence` | 24 | 25 | U | done |
| MAT-3 | Missing data = unknown, not zero; breakdown exposed | 24 | 25 | U | done |
| CMP-1 | Backend enforces exactly two distinct IDs | 25 | — | S/I | done |
| CMP-2 | Criteria set, weights, trade-offs, history | 25 | — | U/E2E | done |
| TLR-1 | Tailored CV as new immutable version; master unchanged | 29 | 30 | I | done |
| TLR-2 | Before/after diff; claim-level accept/reject; ID + EN | 29 | — | E2E | done |
| TLR-3 | Cover letter draft | 29 | — | U | done |
| TLR-4 | Never auto-submit | 29, 31 | — | D + code review | done |

## 9. Tracker, PWA, ops, quality (blocks 28–43)

| ID | Requirement | Impl | Also | Test | Status |
|---|---|---|---|---|---|
| TRK-1 | Application statuses + timeline + reminders | 31 | — | I | done |
| TRK-2 | Safe external apply link with displayed domain | 31 | — | U/E2E | done |
| PWA-1 | Manifest, original icons, service worker, update UX | 32 | — | Build output + manifest check | done |
| PWA-2 | Offline shell; no caching of CVs/API/AI data | 32 | 42 | S: cache inspection | done |
| PWA-3 | iOS/Android/desktop install help page | 32 | — | M | done |
| OPS-1 | Source health dashboard from persisted data | 28 | — | I | done |
| OPS-2 | Import history and review queue with audit | 33 | — | E2E | done |
| OPS-3 | Career intelligence with sample sizes and source links | 34 | 18 | U/M | done |
| OPS-4 | Backup/restore (DB, files, encrypted settings, manifest, checksums) | 35 | 40 | I: restore into clean env | done |
| OPS-5 | Personal data export without secrets | 35 | — | S: export scan | done |
| QA-1 | Full test pyramid + evaluation dataset + release gates | 36 | — | CI | done |
| QA-2 | Configurable resource limits; measured optimisation | 37 | — | Load/profiling report | done |
| DEP-1 | Non-root multi-stage images, health checks, named volumes | 38 | — | Docker smoke | done |
| DEP-2 | VPS guide: TLS reverse proxy; DB/Redis not public | 39 | — | D + port scan | done |
| DEP-3 | Migration to another server proven | 40 | — | E2E restore test | done |
| SEC-1 | Auth: sessions, CSRF, throttling, headers, private routes | 07 | 42 | S | done |
| SEC-2 | Final security review, threat model, known limitations | 42 | — | D | done |
| DOC-1 | README + operator handbook match reality | 43 | all | D | done |

## 10. Non-goals (must remain absent)

Verified by code review in Block 42: no auto-apply; no access-control bypass; no private-group/DM scraping; no personal dossiers; no fabricated fields; no hiring-success guarantees; no billing/tenancy/public signup.
