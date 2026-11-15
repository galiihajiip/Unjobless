/**
 * Render every route with mocked API responses (empty and populated) to catch runtime crashes,
 * missing accessible names and dead navigation. Network is fully mocked.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes, makeQueryClient } from '@/App'
import { ToastProvider } from '@/components/ui'

vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: () => ({ needRefresh: [false, () => {}], offlineReady: [false, () => {}], updateServiceWorker: async () => {} }) }))

const vacancy = {
  id: 1, title: 'Data Analyst Intern', company: 'PT Contoh', company_id: 1, classification: 'DIRECT_VACANCY', verification_status: 'VERIFIED_OPEN', freshness: 'NEW',
  status_reason: 'Listed', employment_type: 'INTERNSHIP', work_arrangement: 'HYBRID', seniority: 'INTERN', location: 'Jakarta', salary_min: 3000000, salary_max: 4000000,
  salary_currency: 'IDR', pay_period: 'MONTH', is_paid: true, application_deadline: '2026-12-31', application_url: 'https://x.example/apply', application_domain: 'x.example',
  first_seen_at: '2026-11-01T00:00:00Z', last_seen_at: '2026-11-10T00:00:00Z', last_checked_at: null, last_verified_at: null, source_published_at: null, data_confidence: 0.7,
  candidate_fit_score: 0.5, preference_fit_score: null, overall_score: null, eligible: null, saved_state: null, application_status: null,
  sources: [{ name: 'Acme ATS', category: 'ATS_BOARD', url: 'https://x.example/1', domain: 'x.example', last_seen_at: '2026-11-10T00:00:00Z' }], skills_preview: ['SQL'], warnings: [],
}
const detail = { ...vacancy, redirected_from: null, alternative_title: null, department: null, job_family: null, industry: null, openings_count: null, recruitment_batch: null, internship_duration_months: 6,
  education_level: null, min_semester: null, min_gpa: null, experience_years_min: null, start_date: null, description: 'desc', details: {}, field_meta: {}, skills: [{ skill: 'SQL', required: true }],
  requirements: [], benefits: [], locations: [], source_links: [], evidence: [{ field: 'title', excerpt: 'Data Analyst Intern', origin: 'EXPLICIT', confidence: 0.9, raw_version_id: 1 }],
  history: [{ from: null, to: 'VERIFIED_OPEN', reason: 'r', rule: null, actor: 'SYSTEM', at: '2026-11-01T00:00:00Z' }],
  match: { breakdown: { candidate_fit: [{ name: 'required_skills', score: 0.5, weight: 0.5, detail: '1 of 2', matched: [{ skill: 'SQL', evidence: ['sk_1'] }], missing: ['Tableau'], partial: [] }], preference_fit: [], eligibility_blocks: [], unknowns: ['compensation'], note: 'n' } },
  unknown_fields: ['deadline'], duplicate_candidates: [], saved_note: null }

function routeData(url: string): unknown {
  const u = url.replace(/^\/api/, '').split('?')[0]
  if (u === '/auth/state') return { bootstrapped: true, authenticated: true, setup_token_required: false, display_name: 'Tester' }
  if (u === '/overview') return { counts: { open_vacancies: 1, new_this_week: 1, closing_soon: 0, potential_leads: 0, needs_review: 0 }, sources: { total: 0, enabled: 0, failing: 0, rate_limited: 0, last_run_at: null }, top_matches: [] }
  if (u === '/vacancies') return { items: [vacancy], total: 1, next_cursor: null }
  if (u === '/vacancies/facets') return { status: { VERIFIED_OPEN: 1 }, freshness: {}, employment_type: { INTERNSHIP: 1 }, work_arrangement: {}, cities: [], skills: [], sources: [] }
  if (/^\/vacancies\/\d+$/.test(u)) return detail
  if (u.endsWith('/tailored') || u.endsWith('/cover-letters')) return []
  if (u === '/signals') return { items: [], total: 0 }
  if (u === '/profile') return { active: null, latest_draft: null, versions: [], resumes: [] }
  if (u === '/profile/preferences') return { target_roles: [], job_families: [], industries: [], skills_to_develop: [], employment_types: [], work_arrangements: [], preferred_cities: [], remote_ok: true, commute_area_note: null, min_compensation: null, compensation_currency: 'IDR', compensation_period: 'MONTH', education_level: null, current_semester: null, career_goals: null, excluded_companies: [], excluded_industries: [], excluded_keywords: [], language: 'id' }
  if (u === '/compare/defaults') return { weights: { candidate_fit: 3 }, builtin: {} }
  if (u === '/imports/batches') return { items: [], total: 0 }
  if (u === '/sources/connectors') return []
  if (u === '/ai/usage') return { days: 30, by_task: [], recent_runs: [] }
  if (u === '/ai/tasks') return { tasks: [] }
  if (u === '/ai/budget') return { daily_budget_usd: null, spent_last_24h_usd: 0 }
  if (u === '/settings') return { app: { theme: 'light', language: 'en', raw_retention_days: null, notify_in_app: true, notify_deadline_days: 3, backup_keep: 7 }, limits: { max_urls_per_batch: 50 }, environment: { env: 'test', master_key_configured: true, user_agent: 'ua' } }
  if (u === '/intelligence/summary') return { window: { start: '', end: '', days: 90 }, min_sample: 5, topics: [], sentiment_by_target: [], common_skills: [], vacancies_in_window: 0, top_hiring_companies: [], caveat: 'c' }
  if (u === '/intelligence/trends') return { series: [], note: 'n' }
  return []
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(routeData(url)), { headers: { 'content-type': 'application/json' } })))
})
afterEach(() => vi.unstubAllGlobals())

const PAGES: [string, string | RegExp][] = [
  ['/', /Hello, Tester/],
  ['/discover', 'Discover'],
  ['/vacancies/1', 'Data Analyst Intern'],
  ['/signals', 'Opportunity Signals'],
  ['/compare', 'Compare'],
  ['/applications', 'Applications'],
  ['/applications/tailor/1', 'Tailor your application'],
  ['/profile', 'My Career Profile'],
  ['/profile?tab=preferences', 'My Career Profile'],
  ['/import', 'Import Center'],
  ['/sources', 'Sources'],
  ['/intelligence', 'Career Intelligence'],
  ['/ai', 'AI Studio'],
  ['/settings', 'Settings'],
  ['/settings/install', 'Install Unjobless'],
]

test.each(PAGES)('renders %s', async (path, heading) => {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  )
  expect(await screen.findByRole('heading', { level: 1, name: heading }, { timeout: 3000 })).toBeInTheDocument()
  // every button has an accessible name
  for (const b of screen.queryAllByRole('button')) expect(b).toHaveAccessibleName()
})

test('vacancy detail shows unknowns and evidence-backed fit', async () => {
  const router = createMemoryRouter(routes, { initialEntries: ['/vacancies/1'] })
  render(<QueryClientProvider client={makeQueryClient()}><ToastProvider><RouterProvider router={router} /></ToastProvider></QueryClientProvider>)
  expect(await screen.findByText(/Not stated by the source/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Apply on original site/ })).toBeInTheDocument()
})
