import { ArrowUpRight, CheckCircle2, Circle, Compass, DatabaseZap, Download, Radar, UserRound } from 'lucide-react'
import { Link } from 'react-router'
import { Card, ErrorState, LoadingCards, Meter, PageHeader } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { fmtRelative } from '@/lib/format'
import { useGet } from '@/lib/queries'

interface Overview {
  counts: { open_vacancies: number; new_this_week: number; closing_soon: number; potential_leads: number; needs_review: number }
  sources: { total: number; enabled: number; failing: number; rate_limited: number; last_run_at: string | null }
  top_matches: { id: number; title: string; company: string | null; overall_score: number | null; candidate_fit_score: number | null; preference_fit_score: number | null }[]
}

export default function OverviewPage() {
  const { state } = useAuth()
  const ov = useGet<Overview>(['overview'], '/overview')
  const profile = useGet<{ active: unknown }>(['profile'], '/profile')
  const prefs = useGet<{ target_roles: string[] }>(['prefs'], '/profile/preferences')
  const ai = useGet<{ id: number }[]>(['ai-providers'], '/ai/providers')
  const steps = [
    { done: !!profile.data?.active, label: 'Upload and confirm your CV', to: '/profile', icon: UserRound },
    { done: (prefs.data?.target_roles?.length ?? 0) > 0, label: 'Set your career preferences', to: '/profile?tab=preferences', icon: Compass },
    { done: (ov.data?.sources.enabled ?? 0) > 0, label: 'Enable at least one permitted source', to: '/sources', icon: DatabaseZap },
    { done: (ov.data?.counts.open_vacancies ?? 0) > 0, label: 'Import a vacancy URL or pasted post', to: '/import', icon: Download },
    { done: (ai.data?.length ?? 0) > 0, label: 'Optional: add an AI provider for richer extraction', to: '/ai', icon: Radar },
  ]
  const remaining = steps.filter((s) => !s.done).length
  return (
    <>
      <PageHeader
        eyebrow={<span className="badge badge-brand">Discover broadly · Understand deeply · Apply deliberately</span>}
        title={`Hello${state?.display_name ? `, ${state.display_name}` : ''}`}
        description="Your private career workspace: what is new, what fits, and what needs your attention."
      />
      {ov.isLoading ? (
        <LoadingCards count={3} />
      ) : ov.error ? (
        <ErrorState error={ov.error} onRetry={() => void ov.refetch()} />
      ) : ov.data ? (
        <div className="stack-lg">
          <div className="grid grid-4">
            <Stat label="Open vacancies" value={ov.data.counts.open_vacancies} to="/discover" />
            <Stat label="New this week" value={ov.data.counts.new_this_week} to="/discover?sort=newest" />
            <Stat label="Closing within 7 days" value={ov.data.counts.closing_soon} to="/discover?freshness=CLOSING_SOON" />
            <Stat label="Imports to review" value={ov.data.counts.needs_review} to="/import?tab=review" />
          </div>
          <div className="grid grid-2">
            <Card>
              <div className="card-title">
                <h2 style={{ fontSize: 'var(--text-lg)' }}>Best current matches</h2>
                <Link to="/discover?sort=best_fit" className="small">See all</Link>
              </div>
              {ov.data.top_matches.length === 0 ? (
                <p className="secondary small">Matches appear once your profile is confirmed and vacancies are collected. Scores are transparent heuristics, not hiring predictions.</p>
              ) : (
                <ul className="list-plain stack">
                  {ov.data.top_matches.map((m) => (
                    <li key={m.id} className="row-between">
                      <Link to={`/vacancies/${m.id}`} className="stack-sm" style={{ gap: 0, textDecoration: 'none', color: 'inherit', minWidth: 0 }}>
                        <strong className="truncate">{m.title}</strong>
                        <span className="small muted">{m.company ?? 'Unknown company'}</span>
                      </Link>
                      <Meter value={m.overall_score} label="Overall" />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <div className="card-title">
                <h2 style={{ fontSize: 'var(--text-lg)' }}>Sources</h2>
                <Link to="/sources" className="small">Manage</Link>
              </div>
              <dl className="kv">
                <dt>Enabled</dt>
                <dd className="num">{ov.data.sources.enabled} of {ov.data.sources.total}</dd>
                <dt>Need attention</dt>
                <dd className="num">{ov.data.sources.failing + ov.data.sources.rate_limited}</dd>
                <dt>Last collection</dt>
                <dd>{ov.data.sources.last_run_at ? fmtRelative(ov.data.sources.last_run_at) : 'Never'}</dd>
                <dt>Unverified leads</dt>
                <dd className="num">
                  <Link to="/signals">{ov.data.counts.potential_leads}</Link>
                </dd>
              </dl>
              <p className="xs muted" style={{ marginTop: 'var(--space-3)' }}>Coverage is limited to the sources you enable and the content you import — never the whole internet.</p>
            </Card>
          </div>
          {remaining > 0 && (
            <Card tone="soft">
              <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-3)' }}>Get set up ({steps.length - remaining}/{steps.length})</h2>
              <ul className="list-plain stack-sm">
                {steps.map((s) => (
                  <li key={s.label}>
                    <Link to={s.to} className="row" style={{ textDecoration: 'none', color: s.done ? 'var(--foreground-muted)' : 'inherit' }}>
                      {s.done ? <CheckCircle2 size={18} color="var(--success)" aria-label="Done" /> : <Circle size={18} aria-label="To do" />}
                      <span style={{ textDecoration: s.done ? 'line-through' : 'none' }}>{s.label}</span>
                      {!s.done && <ArrowUpRight size={14} aria-hidden="true" />}
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      ) : null}
    </>
  )
}

function Stat({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Link to={to} className="card card-link stack-sm">
      <span className="small secondary">{label}</span>
      <span className="num" style={{ fontSize: 'var(--text-3xl)', fontWeight: 750, letterSpacing: '-0.03em' }}>{value}</span>
    </Link>
  )
}
