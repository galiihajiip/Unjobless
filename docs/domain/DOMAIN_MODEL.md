# Unjobless — Domain Model

Status: Accepted (Block 02). Source of truth for the schema in Block 06. Enum values below are the exact strings stored in the database (`backend/src/unjobless/domain/enums.py`).

## 1. Bounded modules

| Module | Aggregates |
|---|---|
| **Owner & settings** | `owner_account`, `app_settings`, `sessions`, `audit_events` |
| **Sources & collection** | `sources` (+ config, policy review, cursors, health events, exclusions), `source_runs`, `source_run_items` |
| **Ingestion & evidence** | `raw_source_documents`, `raw_source_versions`, `source_media_assets`, `content_transcriptions`, `import_batches`, `import_items` |
| **Intelligence** | `companies` (+ aliases), `job_vacancies` (+ sources, requirements, skills, benefits, locations, evidence, status history), `opportunity_signals` (+ entities), `sentiment_analyses`, `topic_observations`, `trend_observations`, `deduplication_candidates` |
| **Profile** | `candidate_profiles`, `candidate_profile_versions` (+ sections), `resume_documents`, `resume_extractions`, `career_preferences` |
| **Decisioning** | `match_analyses`, `job_comparisons` (+ items, weights), `saved_opportunities`, `application_records` (+ status history), `tailored_resumes`, `cover_letters`, `user_notes` |
| **AI & operations** | `ai_provider_configs`, `ai_model_configs`, `ai_prompt_versions`, `ai_usage_events`, `ai_task_runs`, `processing_jobs`, `backup_records` |

## 2. Core separations (acceptance criteria)

1. **Raw vs normalized.** `raw_source_documents/versions` hold exactly what was collected (immutable). `job_vacancies` and `opportunity_signals` are derived and always reference the raw version(s) and evidence spans they came from.
2. **Direct vacancy vs unverified signal.** A `job_vacancies` row represents a concrete, actionable opening. An `opportunity_signals` row represents informal or unverified content (lead, referral, rumour, discussion). A signal can be *promoted* to a vacancy only through an explicit verification action (user review or evidence rule), recorded in `vacancy_status_history` and linked via `opportunity_signals.promoted_vacancy_id`.
3. **Sentiment vs opportunity.** `sentiment_analyses` and `topic_observations` are separate tables keyed to raw versions. No code path writes vacancy status from sentiment.
4. **One vacancy, many sources.** `job_vacancy_sources(vacancy_id, raw_document_id)` is many-to-one to the vacancy; each keeps its own URLs, native IDs and timestamps.
5. **Master vs tailored CV.** `candidate_profile_versions` are immutable once `CONFIRMED`. `tailored_resumes` are new rows referencing the profile version and vacancy; they never mutate the profile.
6. **Comparison max two.** `job_comparison_items.position` has `CHECK (position IN (1,2))` and `UNIQUE(comparison_id, position)` plus `UNIQUE(comparison_id, vacancy_id)`; the service and API also require exactly two distinct IDs.

## 3. Entities (key fields)

### Sources & collection
- **Source** — `id`, `key` (unique slug), `name`, `domain`, `category: SourceCategory`, `connector_type` (registry key), `collection_method: CollectionMethod`, `documentation_url`, `terms_url`, `policy_status: PolicyStatus`, `state: SourceState`, `health: SourceHealth`, `config` (JSONB, validated by connector schema), `secret_ref` (→ encrypted secret, nullable), `schedule_interval_seconds`, `next_run_at`, `rate_limit_per_minute`, `max_concurrency`, `last_success_at`, `last_attempt_at`, `consecutive_failures`, timestamps.
- **SourcePolicyReview** — `source_id`, `reviewed_at`, `decision: PolicyStatus`, `robots_summary`, `terms_notes`, `allowed_paths`, `reviewer_note`.
- **SourceExclusion** — `pattern` (domain or URL prefix), `reason`; checked by every fetch.
- **SourceRun** — `source_id`, `trigger: RunTrigger`, `status: RunStatus`, `attempt`, `idempotency_key` (unique), `started_at`, `finished_at`, `heartbeat_at`, counters (`discovered`, `new`, `changed`, `unchanged`, `duplicates`, `errors`), `error_code`, `error_message`, `cursor_before`, `cursor_after`.
- **SourceRunItem** — `run_id`, `external_id`, `url`, `outcome: RunItemOutcome`, `raw_version_id`, `error`.
- **SourceCursor** — `source_id`, `cursor` (JSONB), `updated_at`.
- **SourceHealthEvent** — `source_id`, `health`, `reason`, `at`.

### Ingestion & evidence
- **RawSourceDocument** — identity of a source item: `source_id`, `source_native_id`, `canonical_url`, `original_url`, `collection_method`, `first_collected_at`, `last_collected_at`, `latest_version_id`. Unique on `(source_id, source_native_id)` when native id present, else `(source_id, canonical_url)`.
- **RawSourceVersion** — immutable content snapshot: `document_id`, `content_hash` (sha256 of normalized content), `content_type`, `raw_text` (bounded) or `blob_ref` (file store), `extracted_text`, `metadata` (JSONB, sanitized — no cookies/headers), `source_published_at`, `collected_at`, `language`, `byte_size`. Unique `(document_id, content_hash)`.
- **SourceMediaAsset** — `version_id`, `kind` (image/pdf/audio/video), `url`, `blob_ref`, `mime`, `sha256`, `permitted_download: bool`.
- **ContentTranscription** — `media_id` or `version_id`, `kind: TranscriptionKind` (OCR/ASR/CAPTION/USER_PROVIDED), `origin` (ORIGINAL/USER_PROVIDED/MACHINE_GENERATED), `text`, `engine`, `confidence`.
- **ImportBatch** — `kind` (URL/PASTE), `status: ImportBatchStatus`, `note`, `category_hint`, counts.
- **ImportItem** — `batch_id`, `input_url` or `pasted_text_hash`, `status: ImportItemStatus`, `raw_version_id`, `result_vacancy_id`, `result_signal_id`, `failure_reason`, `retry_count`, `idempotency_key`.

### Intelligence
- **Company** — `name`, `normalized_name`, `legal_name`, `website_domain`, `industry`, `manually_verified`. **CompanyAlias** — `company_id`, `alias`, `normalized_alias`, `source`.
- **JobVacancy** (canonical) — typed columns for every filterable field: `title`, `normalized_title`, `alternative_title`, `company_id`, `classification`, `verification_status`, `freshness`, `employment_type`, `seniority`, `work_arrangement`, `remote_eligibility`, `job_family`, `industry`, `department`, `openings_count`, `internship_duration_months`, `contract_duration_months`, `recruitment_batch`, `application_url`, `canonical_url`, `salary_min`, `salary_max`, `salary_currency`, `pay_period`, `compensation_type`, `is_paid` (nullable), `education_level`, `min_semester`, `min_gpa`, `experience_years_min`, `application_open_date`, `application_deadline`, `start_date`, `first_seen_at`, `last_seen_at`, `last_checked_at`, `last_verified_at`, `source_published_at`, `closed_at`, `status_reason`, `data_confidence`, `description`, `language`, `search_vector` (generated). JSONB `details` for long-tail fields (responsibilities, deliverables, selection stages, documents, working hours, etc.) and `field_meta` (per-field `{origin, confidence, evidence_ids}`).
- **JobVacancySource** — `vacancy_id`, `raw_document_id`, `source_id`, `source_url`, `application_url`, `source_native_id`, `first_seen_at`, `last_seen_at`, `is_primary`.
- **JobRequirement** — `vacancy_id`, `kind` (education/major/skill_required/skill_preferred/language/certification/portfolio/legal/soft_skill/document/experience/other), `value`, `normalized_value`, `origin: FieldOrigin`, `evidence_id`.
- **JobSkill** — `vacancy_id`, `skill`, `normalized_skill`, `required: bool`. **JobBenefit**, **JobLocation** (`city`, `region`, `country`, `is_remote`).
- **JobEvidence** — `vacancy_id` or `signal_id`, `raw_version_id`, `field_name`, `excerpt`, `start_offset`, `end_offset`, `origin: FieldOrigin`, `confidence`.
- **VacancyStatusHistory** — `vacancy_id`, `from_status`, `to_status`, `freshness`, `reason`, `actor` (SYSTEM/USER), `rule`, `at`.
- **OpportunitySignal** — `raw_version_id`, `primary_classification`, `secondary_classifications` (text[]), `signal_type: SignalType`, `confidence`, `verification_recommendation`, `reason`, `ambiguity_flags` (text[]), `company_id`, `role_text`, `location_text`, `application_url`, `status: VerificationStatus`, `promoted_vacancy_id`.
- **SignalEntity** — `signal_id`, `kind`, `value`, `origin`, `evidence_excerpt`.
- **SentimentAnalysis** — `raw_version_id`, `company_id`, `target: SentimentTarget`, `polarity: Sentiment`, `confidence`, `sarcasm_uncertain`, `language`, `evidence_excerpt`, `observed_at`.
- **TopicObservation** — `raw_version_id`, `company_id`, `topic`, `confidence`, `observed_at`. **TrendObservation** — materialized aggregates: `topic|metric`, `company_id`, `window_start`, `window_end`, `count`, `unique_sources`, `unique_companies`.
- **DeduplicationCandidate** — `vacancy_a_id`, `vacancy_b_id`, `score`, `signals` (JSONB), `status` (PENDING/MERGED/REJECTED/AUTO_MERGED), `decided_at`, `undo_payload`.

### Profile
- **ResumeDocument** — `file_sha256`, `blob_ref`, `filename`, `mime`, `byte_size`, `uploaded_at`; immutable.
- **ResumeExtraction** — `resume_id`, `text`, `sections` (JSONB), `warnings`, `ai_task_run_id`.
- **CandidateProfile** — single row for the owner; `active_version_id`.
- **CandidateProfileVersion** — `profile_id`, `version_no`, `status: ProfileVersionStatus`, `source_resume_id`, `data` (JSONB validated by `ProfileData` schema: headline, summary, educations, experiences, organizations, projects, skills, certifications, awards, publications, languages, links), `confirmed_at`. Each fact carries `{id, verified: bool, evidence}`. Typed child tables (`candidate_skills`, …) are **not** split out in v1: the profile is edited and versioned as one validated document, which keeps versioning trivial; skills are indexed via a materialized `candidate_skills` view for matching.
- **CareerPreferences** — target roles, industries, skills to develop, employment types, work arrangements, cities, remote_ok, min_compensation (+ currency, period), education/semester, goals, exclusions.

### Decisioning
- **MatchAnalysis** — `vacancy_id`, `profile_version_id`, `preferences_hash`, `candidate_fit_score` (nullable), `preference_fit_score` (nullable), `data_confidence_score`, `overall_score` (nullable), `weights` (JSONB), `breakdown` (JSONB: matched/partial/missing/unknown items with evidence), `algorithm_version`, `computed_at`. Unique `(vacancy_id, profile_version_id, preferences_hash, algorithm_version)`.
- **JobComparison** — `weights` (JSONB), `result` (JSONB), `created_at`. **JobComparisonItem** — `comparison_id`, `vacancy_id`, `position ∈ {1,2}`.
- **SavedOpportunity** — `vacancy_id` or `signal_id`, `state: SavedState` (SAVED/INTERESTING/DISMISSED/ARCHIVED/REPORTED), `note`.
- **ApplicationRecord** — `vacancy_id`, `status: ApplicationStatus`, `applied_at`, `follow_up_at`, `deadline`, `tailored_resume_id`, `cover_letter_id`, `notes`; **ApplicationStatusHistory**.
- **TailoredResume** — `vacancy_id`, `profile_version_id`, `language`, `content` (JSONB claims with evidence refs and accept state), `generation_settings`, `ai_task_run_id`, `template`, `created_at`. **CoverLetter** — similar. **ExportFile** — `owner_type/id`, `format`, `blob_ref`, `template`.

### AI & operations
- **AIProviderConfig** — `name`, `kind` (anthropic/openai_compatible/fake), `base_url`, `encrypted_api_key` (bytea), `key_fingerprint`, `key_hint` (last 4), `is_default`, `enabled`, `cooldown_until`.
- **AIModelConfig** — `provider_id`, `model`, `input_price_per_mtok`, `output_price_per_mtok`, `max_output_tokens`. Task routing in `app_settings.ai_task_routes`.
- **AIPromptVersion** — `task`, `version`, `template_hash`, `schema_version`.
- **AITaskRun** — `task`, `status: AITaskStatus`, `provider_id`, `model`, `prompt_version`, `schema_version`, `input_ref`, `output` (JSONB), `error`, `attempts`.
- **AIUsageEvent** — `task_run_id`, `input_tokens`, `output_tokens`, `cost_estimate`, `at`.
- **AuditEvent** — `actor`, `action`, `target_type`, `target_id`, `details` (redacted), `at`.

## 4. Typed columns vs JSONB

| Typed columns | JSONB |
|---|---|
| Anything filtered, sorted, joined, constrained or aggregated: status, classification, dates, compensation numbers, work arrangement, employment type, scores, foreign keys, URLs | Connector raw payload metadata; per-field metadata (`field_meta`); long-tail vacancy details (responsibilities, selection stages, working hours, documents); profile version document; match breakdowns; comparison results; AI raw output; source connector config |

## 5. Enumerations

| Enum | Values |
|---|---|
| SourceCategory | `JOB_API`, `ATS_BOARD`, `CAREER_PAGE`, `RSS_FEED`, `SITEMAP`, `PUBLIC_WEB`, `SOCIAL_API`, `FORUM`, `USER_URL`, `USER_PASTE`, `USER_DOCUMENT` |
| CollectionMethod | `OFFICIAL_API`, `ATS_PUBLIC_API`, `HTML_CRAWL`, `RSS`, `SITEMAP`, `STRUCTURED_DATA`, `USER_URL_IMPORT`, `USER_PASTE`, `USER_UPLOAD` |
| PolicyStatus | `UNREVIEWED`, `APPROVED`, `RESTRICTED`, `DENIED` |
| SourceState | `ENABLED`, `PAUSED`, `DISABLED` |
| SourceHealth | `UNKNOWN`, `HEALTHY`, `DEGRADED`, `FAILING`, `RATE_LIMITED`, `UNAVAILABLE` |
| RunTrigger | `SCHEDULE`, `MANUAL`, `RECHECK`, `IMPORT` |
| RunStatus | `QUEUED`, `RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`, `RETRY_SCHEDULED` |
| RunItemOutcome | `NEW`, `CHANGED`, `UNCHANGED`, `DUPLICATE`, `SKIPPED`, `ERROR` |
| ImportBatchStatus | `PENDING`, `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS` |
| ImportItemStatus | `QUEUED`, `FETCHING`, `EXTRACTED`, `NEEDS_REVIEW`, `SAVED`, `DUPLICATE`, `BLOCKED`, `UNAVAILABLE`, `FAILED`, `REJECTED` |
| OpportunityClassification | `DIRECT_VACANCY`, `INFORMAL_OPPORTUNITY_LEAD`, `REFERRAL_SIGNAL`, `RECRUITMENT_CAMPAIGN`, `CAREER_PROGRAM`, `SCHOLARSHIP_OR_COMPETITION`, `EMPLOYER_DISCUSSION`, `EMPLOYER_REVIEW`, `CAREER_TREND`, `IRRELEVANT` |
| SignalType | `DIRECT_HIRING`, `POSSIBLE_HIRING`, `REFERRAL_AVAILABLE`, `FUTURE_HIRING_INTENT`, `APPLICATION_INVITATION`, `RECRUITMENT_BATCH`, `CAREER_EVENT`, `NOT_AN_OPPORTUNITY` |
| VerificationStatus | `NEW_UNREVIEWED`, `NEEDS_REVIEW`, `POTENTIAL_LEAD`, `VERIFIED_OPEN`, `LIKELY_OPEN`, `STATUS_UNKNOWN`, `CLOSED`, `EXPIRED`, `REJECTED_AS_IRRELEVANT`, `SOURCE_UNAVAILABLE` |
| FreshnessState | `NEW`, `ACTIVE`, `CLOSING_SOON`, `STALE`, `EXPIRED`, `UNKNOWN` |
| FieldOrigin | `EXPLICIT`, `INFERRED`, `USER_PROVIDED`, `MISSING` |
| EmploymentType | `FULL_TIME`, `PART_TIME`, `CONTRACT`, `INTERNSHIP`, `FREELANCE`, `TEMPORARY`, `TRAINEE`, `VOLUNTEER`, `UNKNOWN` |
| WorkArrangement | `ONSITE`, `HYBRID`, `REMOTE`, `FLEXIBLE`, `UNKNOWN` |
| Seniority | `INTERN`, `ENTRY`, `JUNIOR`, `MID`, `SENIOR`, `LEAD`, `MANAGER`, `EXECUTIVE`, `UNKNOWN` |
| PayPeriod | `HOUR`, `DAY`, `WEEK`, `MONTH`, `YEAR`, `PROJECT`, `UNKNOWN` |
| Sentiment | `POSITIVE`, `NEUTRAL`, `NEGATIVE`, `MIXED`, `UNCERTAIN` |
| SentimentTarget | `COMPANY`, `RECRUITMENT_PROCESS`, `INTERVIEW`, `INTERNSHIP_EXPERIENCE`, `MANAGEMENT`, `WORK_CULTURE`, `COMPENSATION`, `WORKLOAD`, `ROLE`, `JOB_SEARCH` |
| ProfileVersionStatus | `DRAFT`, `CONFIRMED`, `SUPERSEDED` |
| ApplicationStatus | `SAVED`, `SHORTLISTED`, `PREPARING`, `APPLIED`, `ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `WITHDRAWN`, `ARCHIVED` |
| AITaskStatus | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED_VALIDATION`, `FAILED_PROVIDER`, `RATE_LIMITED`, `CANCELLED` |

`SCHOLARSHIP_OR_COMPETITION` exists in the enum but is excluded from the default job feed (separate filter), per playbook §9.
