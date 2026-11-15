import { ArrowUpRight, Radar, ThumbsDown } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ClassBadge, VerificationBadge } from '@/components/domain/StatusBadge'
import { Alert, Badge, Button, Card, Checkbox, Dialog, EmptyState, ErrorState, LoadingCards, PageHeader, Tabs, TextInput } from '@/components/ui'
import { post, qs } from '@/lib/api'
import { fmtRelative, humanize } from '@/lib/format'
import { useAction, useGet } from '@/lib/queries'
import type { Paged, Signal } from '@/lib/types'

type Filter = 'leads' | 'referrals' | 'campaigns' | 'all'
const FILTERS: Record<Filter, string[]> = {
  leads: ['INFORMAL_OPPORTUNITY_LEAD'],
  referrals: ['REFERRAL_SIGNAL'],
  campaigns: ['RECRUITMENT_CAMPAIGN', 'CAREER_PROGRAM', 'SCHOLARSHIP_OR_COMPETITION'],
  all: [],
}

export default function SignalsPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  const [promote, setPromote] = useState<Signal | null>(null)
  const list = useGet<Paged<Signal>>(['signals', filter, search], `/signals${qs({ classification: FILTERS[filter], q: search, limit: 50 })}`)
  const reject = useAction((id: number) => post(`/signals/${id}/status`, { status: 'REJECTED_AS_IRRELEVANT' }), { invalidate: [['signals']], success: 'Marked as irrelevant' })
  return (
    <>
      <PageHeader title="Opportunity Signals" description="Informal leads, referral offers and recruitment announcements. These are not verified vacancies — check them before acting." />
      <Alert tone="info">A high confidence score never makes a lead “verified”. Promote a lead only after you have confirmed the opening yourself.</Alert>
      <div className="row-between" style={{ margin: 'var(--space-4) 0' }}>
        <Tabs<Filter> label="Signal type" value={filter} onChange={setFilter} items={[{ value: 'all', label: 'All' }, { value: 'leads', label: 'Leads' }, { value: 'referrals', label: 'Referrals' }, { value: 'campaigns', label: 'Programs & campaigns' }]} idPrefix="sig" />
        <form role="search" onSubmit={(e) => { e.preventDefault(); setSearch(q) }} className="search-input" style={{ flex: '0 1 320px' }}>
          <Radar size={18} aria-hidden="true" />
          <label className="sr-only" htmlFor="sig-q">Search signals</label>
          <input id="sig-q" className="input" placeholder="Search signals" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
      </div>
      <div id="sig-panel" role="tabpanel" className="stack">
        {list.isLoading ? (
          <LoadingCards />
        ) : list.error ? (
          <ErrorState error={list.error} onRetry={() => void list.refetch()} />
        ) : !list.data?.items.length ? (
          <EmptyState icon={<Radar size={28} />} title="No signals here">Signals come from enabled sources and pasted posts (e.g. referral offers or “we're opening a batch soon”).</EmptyState>
        ) : (
          list.data.items.map((s) => (
            <Card key={s.id} className="stack-sm">
              <div className="row-between">
                <div className="row" style={{ gap: 6 }}>
                  <ClassBadge value={s.classification} />
                  <VerificationBadge status={s.status} />
                  <Badge tone="outline">{Math.round(s.confidence * 100)}% confidence</Badge>
                </div>
                <span className="xs muted">{fmtRelative(s.observed_at)} · {s.source.name}{s.source.author_label ? ` · ${s.source.author_label}` : ''}</span>
              </div>
              {(s.role || s.company) && <h3>{[s.role, s.company].filter(Boolean).join(' · ')}</h3>}
              <p className="secondary small reading wrap-anywhere">{s.summary}</p>
              {s.reason && <p className="xs muted">Why: {s.reason}</p>}
              {s.ambiguity_flags.length > 0 && <div className="chip-list">{s.ambiguity_flags.map((f) => <Badge key={f} tone="warning">{humanize(f)}</Badge>)}</div>}
              {s.entities.length > 0 && (
                <dl className="kv">
                  {s.entities.map((e, i) => (
                    <div key={i} style={{ display: 'contents' }}>
                      <dt>{humanize(e.kind)}</dt>
                      <dd>{e.kind === 'application_url' ? <a href={e.value} target="_blank" rel="noopener noreferrer">{e.value}</a> : e.value} {e.origin !== 'EXPLICIT' && <span className="xs muted">({humanize(e.origin)})</span>}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <div className="row">
                {s.source.url && <a className="btn btn-ghost btn-sm" href={s.source.url} target="_blank" rel="noopener noreferrer">Original post <ArrowUpRight size={14} /></a>}
                {s.promoted_vacancy_id ? (
                  <a className="btn btn-secondary btn-sm" href={`/vacancies/${s.promoted_vacancy_id}`}>Open vacancy</a>
                ) : (
                  <Button size="sm" variant="secondary" onClick={() => setPromote(s)}>I verified it — promote</Button>
                )}
                {s.status !== 'REJECTED_AS_IRRELEVANT' && <Button size="sm" variant="ghost" icon={<ThumbsDown size={14} />} onClick={() => reject.mutate(s.id)}>Not relevant</Button>}
              </div>
            </Card>
          ))
        )}
      </div>
      {promote && <PromoteDialog s={promote} onClose={() => setPromote(null)} />}
    </>
  )
}

function PromoteDialog({ s, onClose }: { s: Signal; onClose: () => void }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState(s.role ?? '')
  const [company, setCompany] = useState(s.company ?? '')
  const [url, setUrl] = useState(s.application_url ?? '')
  const [confirmed, setConfirmed] = useState(false)
  const act = useAction(() => post<{ vacancy_id: number }>(`/signals/${s.id}/promote`, { title, company: company || null, application_url: url || null, confirm_open: confirmed }), {
    invalidate: [['signals'], ['vacancies']],
    success: 'Promoted to vacancy',
    onSuccess: (r) => navigate(`/vacancies/${r.vacancy_id}`),
  })
  return (
    <Dialog open onClose={onClose} title="Promote lead to vacancy" description="Only do this after confirming the opening exists (e.g. on the company's official page)."
      actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!confirmed || title.length < 2} loading={act.isPending} onClick={() => act.mutate(undefined)}>Promote</Button></>}>
      <TextInput label="Role title" value={title} onChange={(e) => setTitle(e.target.value)} required />
      <TextInput label="Company" value={company} onChange={(e) => setCompany(e.target.value)} />
      <TextInput label="Official application link" type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
      <Checkbox label="I confirmed this opening is real and currently open." checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
    </Dialog>
  )
}
