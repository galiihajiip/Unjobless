# Unjobless — State Machines

Every transition below is implemented as an explicit table in `backend/src/unjobless/domain/state_machines.py` and unit-tested. Transitions not listed are rejected with `InvalidTransition`. Each machine that matters historically writes a history row (`vacancy_status_history`, `application_status_history`, `source_health_events`).

## 1. Source state and health

```mermaid
stateDiagram-v2
  [*] --> DISABLED: created (policy UNREVIEWED)
  DISABLED --> ENABLED: enable (requires policy APPROVED or RESTRICTED)
  ENABLED --> PAUSED: pause
  PAUSED --> ENABLED: resume
  ENABLED --> DISABLED: disable / policy DENIED
  PAUSED --> DISABLED: disable / policy DENIED
```

Guard: a source can be `ENABLED` only if `policy_status ∈ {APPROVED, RESTRICTED}` and it is not matched by a `source_exclusions` entry. Only `ENABLED` sources are scheduled or run.

Health is derived after each run: `HEALTHY` (success) · `DEGRADED` (partial or 1–2 consecutive failures) · `FAILING` (≥3 consecutive failures) · `RATE_LIMITED` (429/quota; cools down until `next_run_at`) · `UNAVAILABLE` (repeated 403/404/blocked) · `UNKNOWN` (never run).

## 2. Collection job (source run / processing job)

```mermaid
stateDiagram-v2
  [*] --> QUEUED
  QUEUED --> RUNNING: claimed by worker
  QUEUED --> CANCELLED
  RUNNING --> SUCCEEDED
  RUNNING --> PARTIAL: some items failed
  RUNNING --> RETRY_SCHEDULED: retryable error, attempts left
  RUNNING --> FAILED: non-retryable / attempts exhausted / stale
  RUNNING --> CANCELLED
  RETRY_SCHEDULED --> QUEUED: backoff elapsed
  RETRY_SCHEDULED --> CANCELLED
```

Terminal: `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`. At most one non-terminal run per source (partial unique index).

## 3. Import item

```mermaid
stateDiagram-v2
  [*] --> QUEUED
  QUEUED --> BLOCKED: SSRF / exclusion / policy
  QUEUED --> FETCHING
  FETCHING --> UNAVAILABLE: login, captcha, 4xx/5xx, timeout
  FETCHING --> FAILED: unexpected error
  FETCHING --> EXTRACTED
  QUEUED --> EXTRACTED: paste import (no fetch)
  EXTRACTED --> DUPLICATE: same content already stored
  EXTRACTED --> NEEDS_REVIEW
  NEEDS_REVIEW --> SAVED: user confirms (vacancy or lead)
  NEEDS_REVIEW --> REJECTED: user rejects
  NEEDS_REVIEW --> DUPLICATE: user merges into existing
  UNAVAILABLE --> QUEUED: retry after correction
  FAILED --> QUEUED: retry
  BLOCKED --> QUEUED: retry after correction (re-validated)
```

Batch status: `PENDING` → `PROCESSING` → `COMPLETED` (all items terminal-ok) or `COMPLETED_WITH_ERRORS`. A failing item never fails the batch.

## 4. Opportunity classification

Classification is an *assignment*, not a lifecycle: each analysis yields one primary + optional secondary classes. Re-classification (new version, user correction) writes a new record; the latest user correction wins over model output.

Routing rule after classification:

| Primary | Creates |
|---|---|
| `DIRECT_VACANCY`, `RECRUITMENT_CAMPAIGN` with explicit role + application path | candidate `job_vacancies` (status `NEW_UNREVIEWED` or `NEEDS_REVIEW`) |
| `INFORMAL_OPPORTUNITY_LEAD`, `REFERRAL_SIGNAL`, `CAREER_PROGRAM`, `RECRUITMENT_CAMPAIGN` (incomplete) | `opportunity_signals` (status `POTENTIAL_LEAD`) |
| `EMPLOYER_DISCUSSION`, `EMPLOYER_REVIEW`, `CAREER_TREND` | sentiment/topic records only |
| `IRRELEVANT` | nothing beyond the raw record |

## 5. Verification status (vacancies and signals)

```mermaid
stateDiagram-v2
  [*] --> NEW_UNREVIEWED
  NEW_UNREVIEWED --> NEEDS_REVIEW: low confidence / conflicts
  NEW_UNREVIEWED --> POTENTIAL_LEAD: signal only
  NEW_UNREVIEWED --> LIKELY_OPEN: trusted source, evidence rules met
  NEW_UNREVIEWED --> VERIFIED_OPEN: user confirms / ATS or API live listing
  NEEDS_REVIEW --> VERIFIED_OPEN: user confirms
  NEEDS_REVIEW --> POTENTIAL_LEAD
  NEEDS_REVIEW --> REJECTED_AS_IRRELEVANT
  POTENTIAL_LEAD --> VERIFIED_OPEN: promoted with evidence (user action)
  POTENTIAL_LEAD --> REJECTED_AS_IRRELEVANT
  POTENTIAL_LEAD --> EXPIRED
  LIKELY_OPEN --> VERIFIED_OPEN
  VERIFIED_OPEN --> LIKELY_OPEN: not re-confirmed recently
  LIKELY_OPEN --> STATUS_UNKNOWN: source not reachable / not seen
  VERIFIED_OPEN --> STATUS_UNKNOWN: fetch failed (NOT closed)
  STATUS_UNKNOWN --> VERIFIED_OPEN: re-confirmed
  STATUS_UNKNOWN --> SOURCE_UNAVAILABLE: repeated failures
  SOURCE_UNAVAILABLE --> VERIFIED_OPEN: re-confirmed
  VERIFIED_OPEN --> CLOSED: explicit closure evidence / user
  LIKELY_OPEN --> CLOSED
  STATUS_UNKNOWN --> CLOSED: corroborated removal / user
  VERIFIED_OPEN --> EXPIRED: explicit deadline passed
  LIKELY_OPEN --> EXPIRED
  STATUS_UNKNOWN --> EXPIRED
  CLOSED --> VERIFIED_OPEN: reopened (user / re-listed)
  EXPIRED --> VERIFIED_OPEN: deadline extended (evidence)
```

Hard rules:
- Confidence alone never produces `VERIFIED_OPEN`; it requires (a) user confirmation, or (b) a live listing on an approved API/ATS source.
- A failed fetch moves at most to `STATUS_UNKNOWN`.
- `EXPIRED` requires an **explicit** deadline in the past (evidence-backed); an old publication date alone does not expire a vacancy.
- User corrections are always allowed (any → any) and recorded with `actor=USER`.

## 6. Freshness (derived, recomputed)

`EXPIRED` if status `EXPIRED`/`CLOSED` · `CLOSING_SOON` if explicit deadline within 7 days · `NEW` if first seen < 3 days · `ACTIVE` if last verified < 14 days · `STALE` if last verified ≥ 30 days or never re-checked for 30 days · otherwise `UNKNOWN`. Thresholds live in settings.

## 7. Application status

```mermaid
stateDiagram-v2
  [*] --> SAVED
  SAVED --> SHORTLISTED
  SAVED --> PREPARING
  SHORTLISTED --> PREPARING
  PREPARING --> APPLIED: user marks applied (never automatic)
  APPLIED --> ASSESSMENT
  APPLIED --> INTERVIEW
  ASSESSMENT --> INTERVIEW
  INTERVIEW --> INTERVIEW: next round
  INTERVIEW --> OFFER
  APPLIED --> REJECTED
  ASSESSMENT --> REJECTED
  INTERVIEW --> REJECTED
  OFFER --> ARCHIVED
  REJECTED --> ARCHIVED
  WITHDRAWN --> ARCHIVED
```

Any non-terminal state may go to `WITHDRAWN` or `ARCHIVED`. `ARCHIVED` may return to `SAVED` (unarchive). Backward moves (e.g. corrections) are allowed with `actor=USER` and recorded.

## 8. AI task

```mermaid
stateDiagram-v2
  [*] --> PENDING
  PENDING --> RUNNING
  RUNNING --> SUCCEEDED: output valid
  RUNNING --> RUNNING: one repair retry on format error
  RUNNING --> FAILED_VALIDATION: still invalid
  RUNNING --> RATE_LIMITED: 429 → provider cooldown
  RUNNING --> FAILED_PROVIDER: timeout / 5xx after retries / auth error
  RATE_LIMITED --> PENDING: cooldown elapsed (re-enqueue)
  PENDING --> CANCELLED
```

A failed AI task never writes canonical data.

## 9. Profile version

`DRAFT` (from CV extraction or manual edit) → `CONFIRMED` (user) → `SUPERSEDED` (when a newer version is confirmed). Confirmed versions are immutable; edits create a new `DRAFT`.
