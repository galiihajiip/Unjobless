import { ChartNoAxesCombined } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Alert, Badge, Card, CardTitle, EmptyState, ErrorState, LoadingCards, PageHeader, Select } from '@/components/ui'
import { humanize } from '@/lib/format'
import { useGet } from '@/lib/queries'

interface Summary {
  window: { start: string; end: string; days: number }
  min_sample: number
  topics: { topic: string; count: number; unique_sources: number; unique_companies: number; low_sample: boolean }[]
  sentiment_by_target: { target: string; counts: Record<string, number>; n: number; low_sample: boolean }[]
  common_skills: { skill: string; vacancies: number; share: number | null }[]
  vacancies_in_window: number
  top_hiring_companies: { id: number; name: string; vacancies: number }[]
  caveat: string
}
interface Trends { series: { dimension: string; points: { week: string; count: number; unique_sources: number }[]; change: { direction: string; change?: number; low_sample: boolean }; total: number }[]; note: string }
const POL = ['POSITIVE', 'NEUTRAL', 'MIXED', 'NEGATIVE', 'UNCERTAIN'] as const
const POL_COLOR: Record<string, string> = { POSITIVE: 'var(--success)', NEUTRAL: 'var(--foreground-muted)', MIXED: 'var(--brand-400)', NEGATIVE: 'var(--danger)', UNCERTAIN: 'var(--border-strong)' }

export default function IntelligencePage() {
  const [days, setDays] = useState('90')
  const [metric, setMetric] = useState('topic_mentions')
  const s = useGet<Summary>(['intel', days], `/intelligence/summary?days=${days}`)
  const t = useGet<Trends>(['trends', metric], `/intelligence/trends?metric=${metric}&weeks=12&refresh=true`)
  return (
    <>
      <PageHeader title="Career Intelligence" description="What your sources and imports show over time. Opinions are labelled as sampled public discussion, never as facts about a company."
        actions={<Select label="Window" value={days} onChange={(e) => setDays(e.target.value)} options={[{ value: '30', label: 'Last 30 days' }, { value: '90', label: 'Last 90 days' }, { value: '365', label: 'Last year' }]} />} />
      {s.isLoading ? <LoadingCards /> : s.error ? <ErrorState error={s.error} /> : !s.data ? null : (
        <div className="stack-lg">
          <Alert tone="info">{s.data.caveat} Results with fewer than {s.data.min_sample} observations are marked “small sample”.</Alert>
          <div className="grid grid-2">
            <Card>
              <CardTitle title="Topics observed" as="h2" />
              {!s.data.topics.length ? <p className="small secondary">No topic observations in this window.</p> : (
                <ul className="list-plain stack-sm">
                  {s.data.topics.map((x) => (
                    <li key={x.topic} className="row-between small">
                      <span>{humanize(x.topic)} {x.low_sample && <Badge tone="warning">small sample</Badge>}</span>
                      <span className="num muted">{x.count} posts · {x.unique_sources} sources</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardTitle title="Sampled public sentiment by aspect" as="h2" />
              {!s.data.sentiment_by_target.length ? <p className="small secondary">No third-party discussions observed.</p> : (
                <ul className="list-plain stack">
                  {s.data.sentiment_by_target.map((x) => (
                    <li key={x.target} className="stack-sm">
                      <div className="row-between small"><strong>{humanize(x.target)}</strong><span className="muted num">n={x.n}{x.low_sample && ' · small sample'}</span></div>
                      <div style={{ display: 'flex', height: 10, borderRadius: 99, overflow: 'hidden', background: 'var(--surface-muted)' }} role="img" aria-label={POL.map((p) => `${humanize(p)} ${x.counts[p] ?? 0}`).join(', ')}>
                        {POL.map((p) => (x.counts[p] ? <span key={p} style={{ width: `${(100 * x.counts[p]) / x.n}%`, background: POL_COLOR[p] }} /> : null))}
                      </div>
                      <span className="xs muted">{POL.filter((p) => x.counts[p]).map((p) => `${humanize(p)} ${x.counts[p]}`).join(' · ')}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <CardTitle title={`Skills requested (${s.data.vacancies_in_window} vacancies)`} as="h2" />
              <ul className="list-plain stack-sm">
                {s.data.common_skills.map((x) => (
                  <li key={x.skill} className="row-between small"><span>{x.skill}</span><span className="num muted">{x.vacancies}{x.share != null && ` · ${Math.round(x.share * 100)}%`}</span></li>
                ))}
              </ul>
            </Card>
            <Card>
              <CardTitle title="Companies with most new vacancies" as="h2" />
              <ul className="list-plain stack-sm">
                {s.data.top_hiring_companies.map((c) => <li key={c.id} className="row-between small"><Link to={`/intelligence?company=${c.id}`}>{c.name}</Link><span className="num muted">{c.vacancies}</span></li>)}
              </ul>
            </Card>
          </div>
          <Card className="stack">
            <div className="row-between">
              <h2 style={{ fontSize: 'var(--text-lg)' }}>Weekly trends (12 weeks)</h2>
              <Select label="Metric" value={metric} onChange={(e) => setMetric(e.target.value)} options={[{ value: 'topic_mentions', label: 'Topic mentions' }, { value: 'new_vacancies', label: 'New vacancies' }, { value: 'sentiment', label: 'Sentiment observations' }]} />
            </div>
            {t.isLoading ? <LoadingCards count={1} /> : !t.data?.series.length ? (
              <EmptyState icon={<ChartNoAxesCombined size={28} />} title="Not enough data yet">Trends need observations across several weeks.</EmptyState>
            ) : (
              <div className="grid grid-2">
                {t.data.series.map((sr) => <Spark key={sr.dimension} label={humanize(sr.dimension)} points={sr.points} change={sr.change} total={sr.total} />)}
              </div>
            )}
            {t.data && <p className="xs muted">{t.data.note}</p>}
          </Card>
          <CompanyInsight />
        </div>
      )}
    </>
  )
}

function Spark({ label, points, change, total }: { label: string; points: { week: string; count: number }[]; change: { direction: string; change?: number; low_sample: boolean }; total: number }) {
  const max = Math.max(1, ...points.map((p) => p.count))
  const w = 240
  const h = 56
  const bw = w / Math.max(points.length, 1)
  return (
    <figure className="card card-soft stack-sm" style={{ margin: 0 }}>
      <figcaption className="row-between small"><strong>{label}</strong><span className="muted num">{total} total</span></figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label={`${label}: ${points.map((p) => `${p.week} ${p.count}`).join(', ')}`}>
        {points.map((p, i) => <rect key={p.week} x={i * bw + 2} y={h - (p.count / max) * (h - 4)} width={bw - 4} height={(p.count / max) * (h - 4)} rx="2" fill="var(--brand-400)" />)}
      </svg>
      <span className="xs muted">{change.direction === 'insufficient_data' ? 'Not enough data to describe a change.' : change.direction === 'stable_or_unclear' ? 'No clear change.' : `${humanize(change.direction)} (${Math.round((change.change ?? 0) * 100)}%)`}{change.low_sample && ' · small sample'}</span>
    </figure>
  )
}

function CompanyInsight() {
  const companies = useGet<{ id: number; name: string; vacancies: number }[]>(['companies'], '/companies?limit=100')
  const [id, setId] = useState('')
  const c = useGet<{
    company: { name: string; website_domain: string | null }
    vacancy_activity: { total: number; by_month: Record<string, number>; internship_months_observed: string[]; recurring_internships: boolean; recent: { id: number; title: string; status: string }[] }
    common_skills: { skill: string; count: number }[]
    public_sentiment: { label: string; n: number; low_sample: boolean; observations: { target: string; polarity: string; excerpt: string; source: string; url: string | null; first_party: boolean; sarcasm_uncertain: boolean }[] }
    source_count: number
  }>(['company', id], id ? `/intelligence/companies/${id}` : null)
  return (
    <Card className="stack">
      <h2 style={{ fontSize: 'var(--text-lg)' }}>Company insight</h2>
      <Select label="Company" value={id} onChange={(e) => setId(e.target.value)} options={[{ value: '', label: 'Choose a company…' }, ...(companies.data ?? []).map((x) => ({ value: String(x.id), label: `${x.name} (${x.vacancies})` }))]} />
      {c.data && (
        <div className="grid grid-2">
          <div className="stack-sm">
            <strong>Vacancy activity</strong>
            <span className="small">{c.data.vacancy_activity.total} vacancies observed from {c.data.source_count} source(s).</span>
            {c.data.vacancy_activity.recurring_internships && <Badge tone="info">Internships observed in more than one year</Badge>}
            <ul className="list-plain small">{c.data.vacancy_activity.recent.map((v) => <li key={v.id}><Link to={`/vacancies/${v.id}`}>{v.title}</Link> <span className="muted">· {humanize(v.status)}</span></li>)}</ul>
            <span className="xs muted">Skills: {c.data.common_skills.map((s) => s.skill).join(', ') || '—'}</span>
          </div>
          <div className="stack-sm">
            <strong>{c.data.public_sentiment.label}</strong>
            <span className="xs muted">n={c.data.public_sentiment.n}{c.data.public_sentiment.low_sample && ' · small sample — do not generalise'}</span>
            <ul className="list-plain stack-sm">
              {c.data.public_sentiment.observations.slice(0, 8).map((o, i) => (
                <li key={i} className="small">
                  <Badge tone={o.polarity === 'NEGATIVE' ? 'danger' : o.polarity === 'POSITIVE' ? 'success' : 'neutral'}>{humanize(o.polarity)}</Badge> <span className="muted xs">{humanize(o.target)}{o.first_party ? ' · company statement' : ''}{o.sarcasm_uncertain ? ' · possibly sarcastic' : ''}</span>
                  <blockquote className="evidence" style={{ margin: '4px 0 0' }}>{o.excerpt}</blockquote>
                  {o.url && <a className="xs" href={o.url} target="_blank" rel="noopener noreferrer">{o.source}</a>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Card>
  )
}
