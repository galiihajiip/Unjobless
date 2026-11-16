export interface Paged<T> {
  items: T[]
  total: number
  limit?: number
  offset?: number
  next_cursor?: string | null
}

export interface SourceRef {
  name: string
  category: string
  url: string | null
  domain: string | null
  last_seen_at: string
}

export interface VacancyCard {
  id: number
  title: string
  company: string | null
  company_id: number | null
  classification: string
  verification_status: string
  freshness: string
  status_reason: string | null
  employment_type: string
  work_arrangement: string
  seniority: string
  location: string | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  pay_period: string | null
  is_paid: boolean | null
  application_deadline: string | null
  application_url: string | null
  application_domain: string | null
  first_seen_at: string
  last_seen_at: string
  last_checked_at: string | null
  last_verified_at: string | null
  source_published_at: string | null
  data_confidence: number | null
  candidate_fit_score: number | null
  preference_fit_score: number | null
  overall_score: number | null
  eligible: boolean | null
  saved_state: string | null
  application_status: string | null
  sources: SourceRef[]
  skills_preview: string[]
  warnings: string[]
}

export interface MatchComponent {
  name: string
  score: number | null
  weight: number
  detail: string
  matched: { skill?: string; evidence?: string[]; fact?: string; text?: string }[]
  missing: string[]
  partial: string[]
}

export interface VacancyDetail extends VacancyCard {
  redirected_from: number | null
  alternative_title: string | null
  department: string | null
  job_family: string | null
  industry: string | null
  openings_count: number | null
  recruitment_batch: string | null
  internship_duration_months: number | null
  education_level: string | null
  min_semester: number | null
  min_gpa: number | null
  experience_years_min: number | null
  start_date: string | null
  description: string | null
  details: Record<string, unknown>
  field_meta: Record<string, { origin?: string; confidence?: number }>
  skills: { skill: string; required: boolean }[]
  requirements: { kind: string; value: string }[]
  benefits: { category: string; value: string }[]
  locations: { raw: string; city: string | null; is_remote: boolean }[]
  source_links: {
    source: string
    category: string
    collection_method: string
    url: string | null
    application_url: string | null
    first_seen_at: string
    last_seen_at: string
    raw_version_id: number | null
    gone_at: string | null
  }[]
  evidence: { field: string; excerpt: string; origin: string; confidence: number | null; raw_version_id: number | null }[]
  history: { from: string | null; to: string; reason: string | null; rule: string | null; actor: string; at: string }[]
  match: { breakdown: { candidate_fit: MatchComponent[]; preference_fit: MatchComponent[]; eligibility_blocks: string[]; unknowns: string[]; note: string } } | null
  unknown_fields: string[]
  duplicate_candidates: { id: number; other_id: number; score: number }[]
  saved_note: string | null
}

export interface Signal {
  id: number
  classification: string
  secondary: string[]
  signal_type: string
  confidence: number
  status: string
  recommendation: string
  reason: string | null
  ambiguity_flags: string[]
  company: string | null
  role: string | null
  location: string | null
  application_url: string | null
  summary: string | null
  observed_at: string
  promoted_vacancy_id: number | null
  source: { name: string; category: string; url: string | null; author_label: string | null }
  entities: { kind: string; value: string; origin: string; excerpt: string | null }[]
  evidence: string[]
  raw_version_id: number
}

export interface RunSummary {
  id: number
  status: string
  trigger: string
  attempt: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  retry_at: string | null
  discovered: number
  new: number
  changed: number
  unchanged: number
  duplicates: number
  errors: number
  error_code: string | null
  error_message: string | null
  duration_seconds: number | null
}

export interface Source {
  id: number
  key: string
  name: string
  domain: string | null
  category: string
  connector_type: string
  collection_method: string
  documentation_url: string | null
  terms_url: string | null
  policy_status: string
  policy_notes: string | null
  state: string
  health: string
  health_reason: string | null
  config: Record<string, unknown>
  schedule_interval_seconds: number | null
  next_run_at: string | null
  rate_limit_per_minute: number
  max_concurrency: number
  last_success_at: string | null
  last_attempt_at: string | null
  consecutive_failures: number
  is_system: boolean
  has_secret: boolean
  active_run: RunSummary | null
  last_run: RunSummary | null
  stats: { runs: number; discovered: number; new: number; changed: number; errors: number; avg_duration_seconds: number | null } | null
}

export interface ConnectorInfo {
  type: string
  name: string
  description: string
  category: string
  documentation_url: string | null
  terms_url: string | null
  default_schedule_seconds: number | null
  auth_required: boolean
  terms_review: string
  config_schema: JsonSchema
}

export interface JsonSchema {
  type?: string
  properties?: Record<string, JsonSchema & { description?: string; default?: unknown; title?: string }>
  required?: string[]
  items?: JsonSchema
  anyOf?: JsonSchema[]
  description?: string
  default?: unknown
  $defs?: Record<string, JsonSchema>
  $ref?: string
}

export interface ImportItem {
  id: number
  batch_id: number
  position: number
  input_url: string | null
  detected_domain: string | null
  detected_connector: string | null
  paste_meta: Record<string, string | null> | null
  status: string
  failure_reason: string | null
  failure_code: string | null
  retry_count: number
  result_vacancy_id: number | null
  result_signal_id: number | null
  raw_version_id: number | null
  created_at: string
  updated_at: string
  classification: { primary: string; confidence: number; reason: string; ambiguity_flags: string[]; recommendation: string } | null
  title: string | null
  paste_fallback: boolean
  extraction?: { classification: Record<string, unknown>; extraction?: Extraction; extraction_method?: string } | null
  raw?: { content_type: string; title: string | null; collected_at: string; text: string; raw_text: string | null; metadata: Record<string, unknown>; processing_status: string; processing_error: string | null; truncated: boolean }
  media?: { id: number; kind: string; mime: string; status: string; message: string | null }[]
  transcriptions?: { kind: string; origin: string; engine: string | null; text: string }[]
}

export interface Extraction {
  title: string | null
  company: string | null
  locations: string[]
  work_arrangement: string
  employment_type: string
  seniority: string
  application_url: string | null
  application_email: string | null
  application_deadline: string | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  pay_period: string
  is_paid: boolean | null
  required_skills: string[]
  preferred_skills: string[]
  responsibilities: string[]
  benefits: string[]
  min_gpa: number | null
  min_semester: number | null
  education_level: string | null
  evidence: { field: string; excerpt: string; origin: string; confidence: number }[]
  warnings: string[]
  [key: string]: unknown
}

export interface ImportBatch {
  id: number
  kind: string
  status: string
  note: string | null
  item_count: number
  created_at: string
  counts: Record<string, number>
}

export interface Bullet {
  id: string
  text: string
  verified: boolean
}
export interface ProfileData {
  headline: string | null
  summary: string | null
  contact: { full_name: string | null; email: string | null; phone: string | null; location: string | null }
  links: string[]
  educations: { id: string; institution: string; degree: string | null; field: string | null; start: string | null; end: string | null; gpa: string | null; current_semester: number | null; details: string[]; verified: boolean; evidence: string | null; source: string }[]
  experiences: { id: string; organization: string; title: string; kind: string; location: string | null; start: string | null; end: string | null; bullets: Bullet[]; verified: boolean; evidence: string | null; source: string }[]
  projects: { id: string; name: string; role: string | null; start: string | null; end: string | null; description: string | null; bullets: Bullet[]; technologies: string[]; url: string | null; verified: boolean; evidence: string | null; source: string }[]
  skills: { id: string; name: string; level: string | null; verified: boolean; evidence: string | null; source: string }[]
  certifications: { id: string; name: string; issuer: string | null; date: string | null; verified: boolean; evidence: string | null; source: string }[]
  awards: { id: string; name: string; issuer: string | null; date: string | null; verified: boolean; evidence: string | null; source: string }[]
  publications: { id: string; name: string; issuer: string | null; date: string | null; verified: boolean; evidence: string | null; source: string }[]
  languages: { id: string; language: string; proficiency: string | null; verified: boolean; evidence: string | null; source: string }[]
  warnings: string[]
}

export interface ProfileVersion {
  id: number
  version_no: number
  status: string
  source_resume_id: number | null
  note: string | null
  created_at: string
  confirmed_at: string | null
  data: ProfileData
}

export interface Preferences {
  target_roles: string[]
  job_families: string[]
  industries: string[]
  skills_to_develop: string[]
  employment_types: string[]
  work_arrangements: string[]
  preferred_cities: string[]
  remote_ok: boolean
  commute_area_note: string | null
  min_compensation: number | null
  compensation_currency: string
  compensation_period: string
  education_level: string | null
  current_semester: number | null
  career_goals: string | null
  excluded_companies: string[]
  excluded_industries: string[]
  excluded_keywords: string[]
  language: 'id' | 'en'
}

export interface Criterion {
  criterion: string
  winner: 'A' | 'B' | 'Tie' | 'Unknown'
  a: unknown
  b: unknown
  note: string
  weight: number
}

export interface Comparison {
  id?: number
  a: { id: number; title: string; company: string | null; status: string; freshness: string; candidate_fit_score: number | null; preference_fit_score: number | null; overall_score: number | null; application_url: string | null }
  b: Comparison['a']
  criteria: Criterion[]
  weights: Record<string, number>
  totals: { A: number; B: number; decided_weight: number; total_weight: number }
  coverage: number
  unknown_criteria: string[]
  tradeoffs: string[]
  recommendation: { lean: string; text: string; uncertainty: string }
}

export interface Application {
  id: number
  vacancy_id: number
  status: string
  applied_at: string | null
  follow_up_at: string | null
  deadline: string | null
  notes: string | null
  contact_notes: string | null
  tailored_resume_id: number | null
  cover_letter_id: number | null
  updated_at: string
  vacancy: { title: string; company: string | null; status: string; application_url: string | null; location: string | null } | null
  history?: { from: string | null; to: string; note: string | null; at: string }[]
}

export interface Claim {
  id: string
  section: string
  original: string | null
  proposed: string
  fact_ids: string[]
  issues: string[]
  accepted: boolean | null
  source: string
  edited_by_owner?: boolean
}

export interface Tailored {
  id: number
  vacancy_id: number
  parent_id: number | null
  language: string
  finalized: boolean
  template: string
  created_at: string
  content: { claims: Claim[]; missing_requirements: string[]; needs_user_confirmation: string[]; method: string; ai_note?: string }
  sections: { title: string; items: { title?: string; meta?: string; text?: string; bullets?: string[]; url?: string }[] }[]
  preview: { contact: { full_name: string | null; email: string | null; phone: string | null; location: string | null }; headline: string | null; links: string[] }
  exports: { id: number; format: string; template: string; filename: string; created_at: string }[]
}

export interface AIProvider {
  id: number
  name: string
  kind: string
  base_url: string | null
  has_key: boolean
  key_hint: string | null
  key_fingerprint: string | null
  default_model: string | null
  is_default: boolean
  enabled: boolean
  allow_as_fallback: boolean
  cooldown_until: string | null
  last_error: string | null
  last_tested_at: string | null
}
