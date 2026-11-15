import { AlertTriangle, BriefcaseBusiness, FileText, Flag, History, Link2, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApplyButton } from '@/components/domain/ApplyButton'
import { ScoreRow } from '@/components/domain/Scores'
import { FreshnessBadge, VerificationBadge } from '@/components/domain/StatusBadge'
import { Alert, Badge, Button, Card, CardTitle, Dialog, ErrorState, LoadingCards, Meter, PageHeader, Select, Tabs, TextArea } from '@/components/ui'
import { post, put } from '@/lib/api'
import { fmtDate, fmtMoney, fmtRelative, humanize } from '@/lib/format'
import { useAction, useGet } from '@/lib/queries'
import type { MatchComponent, VacancyDetail } from '@/lib/types'

type Tab = 'overview' | 'fit' | 'evidence' | 'sources'

export default function VacancyDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const q = useGet<VacancyDetail>(['vacancy', id], `/vacancies/${id}`)
  const [tab, setTab] = useState<Tab>('overview')
  const [statusOpen, setStatusOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const track = useAction(() => post(`/applications/${id}`), { invalidate: [['vacancy', id], ['applications']], success: 'Added to Applications' })
  if (q.isLoading) return <LoadingCards count={3} />
  if (q.error || !q.data) return <ErrorState error={q.error ?? new Error('Not found')} onRetry={() => void q.refetch()} />
  const v = q.data
  const meta = (f: string) => v.field_meta?.[f]?.origin
  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Discover', to: '/discover' }, { label: v.title }]}
        eyebrow={
          <div className="row" style={{ gap: 6 }}>
            <VerificationBadge status={v.verification_status} title={v.status_reason ?? undefined} />
            <FreshnessBadge value={v.freshness} />
            <Badge>{humanize(v.classification)}</Badge>
          </div>
        }
        title={v.title}
        description={
          <span>
            {v.company ?? 'Company not stated'} · {v.location ?? (v.work_arrangement === 'REMOTE' ? 'Remote' : 'Location not stated')}
            {v.status_reason && <span className="muted"> — {v.status_reason}</span>}
          </span>
        }
        actions={
          <>
            <ApplyButton vacancyId={v.id} disabled={!v.application_url && !v.details?.application_email} />
            {v.application_status ? (
              <Link className="btn btn-secondary" to="/applications">Tracked · {humanize(v.application_status)}</Link>
            ) : (
              <Button icon={<BriefcaseBusiness size={16} />} loading={track.isPending} onClick={() => track.mutate(undefined)}>Track</Button>
            )}
            <Button variant="ai" icon={<FileText size={16} />} onClick={() => navigate(`/applications/tailor/${v.id}`)}>Tailor CV</Button>
          </>
        }
      />
      {v.redirected_from && <Alert tone="info">Vacancy #{v.redirected_from} was merged into this record. All source references are kept below.</Alert>}
      {v.eligible === false && v.match?.breakdown.eligibility_blocks.length ? (
        <Alert tone="warning" title="Possible eligibility issue">
          {v.match.breakdown.eligibility_blocks.join(' ')}
        </Alert>
      ) : null}
      <div className="two-col" style={{ marginTop: 'var(--space-4)' }}>
        <div className="stack">
          <Tabs<Tab>
            label="Vacancy sections"
            idPrefix="vac"
            value={tab}
            onChange={setTab}
            items={[
              { value: 'overview', label: 'Overview' },
              { value: 'fit', label: 'Fit' },
              { value: 'evidence', label: 'Evidence', count: v.evidence.length },
              { value: 'sources', label: 'Sources', count: v.source_links.length },
            ]}
          />
          <div id="vac-panel" role="tabpanel" aria-labelledby={`vac-${tab}`} className="stack">
            {tab === 'overview' && (
              <>
                <Card>
                  <CardTitle title="Key facts" />
                  <dl className="kv">
                    <Fact k="Employment" v={humanize(v.employment_type)} origin={meta('employment_type')} />
                    <Fact k="Arrangement" v={humanize(v.work_arrangement)} origin={meta('work_arrangement')} />
                    <Fact k="Seniority" v={humanize(v.seniority)} />
                    <Fact k="Pay" v={v.salary_min != null ? fmtMoney(v.salary_min, v.salary_max, v.salary_currency, v.pay_period) : v.is_paid === false ? 'Unpaid (stated)' : 'Not stated'} origin={meta('salary_min')} />
                    <Fact k="Deadline" v={v.application_deadline ? fmtDate(v.application_deadline) : 'Not stated'} origin={meta('application_deadline')} />
                    <Fact k="Start date" v={v.start_date ? fmtDate(v.start_date) : null} />
                    <Fact k="Duration" v={v.internship_duration_months ? `${v.internship_duration_months} months` : null} />
                    <Fact k="Education" v={v.education_level ? humanize(v.education_level) : null} />
                    <Fact k="Min. semester" v={v.min_semester} />
                    <Fact k="Min. GPA" v={v.min_gpa} origin={meta('min_gpa')} />
                    <Fact k="Experience" v={v.experience_years_min != null ? `${v.experience_years_min}+ years` : null} />
                    <Fact k="Department" v={v.department} />
                    <Fact k="Openings" v={v.openings_count} />
                  </dl>
                </Card>
                {v.unknown_fields.length > 0 && (
                  <Alert tone="info" title="Not stated by the source">
                    {v.unknown_fields.join(', ')}. Unjobless does not guess these.
                  </Alert>
                )}
                {v.skills.length > 0 && (
                  <Card>
                    <CardTitle title="Skills" />
                    <div className="chip-list">
                      {v.skills.map((s) => (
                        <Badge key={s.skill} tone={s.required ? 'brand' : 'outline'}>{s.skill}{!s.required && ' (preferred)'}</Badge>
                      ))}
                    </div>
                  </Card>
                )}
                <ListCard title="Responsibilities" items={(v.details?.responsibilities as string[]) ?? []} />
                <ListCard title="Requirements" items={v.requirements.map((r) => `${humanize(r.kind)}: ${r.value}`)} />
                <ListCard title="Benefits" items={v.benefits.map((b) => b.value)} />
                <ListCard title="Selection stages" items={(v.details?.selection_stages as string[]) ?? []} />
                {v.description && (
                  <Card>
                    <CardTitle title="Original description" />
                    <pre className="raw reading">{v.description}</pre>
                  </Card>
                )}
              </>
            )}
            {tab === 'fit' && <FitPanel v={v} />}
            {tab === 'evidence' && (
              <Card>
                <CardTitle title="Field evidence" />
                {v.evidence.length === 0 ? (
                  <p className="secondary small">No field-level evidence recorded.</p>
                ) : (
                  <ul className="list-plain stack">
                    {v.evidence.map((e, i) => (
                      <li key={i} className="stack-sm">
                        <div className="row small">
                          <strong>{humanize(e.field)}</strong>
                          <Badge tone={e.origin === 'EXPLICIT' ? 'success' : e.origin === 'USER_PROVIDED' ? 'info' : 'warning'}>{humanize(e.origin)}</Badge>
                          {e.confidence != null && <span className="muted num xs">{Math.round(e.confidence * 100)}%</span>}
                        </div>
                        <blockquote className="evidence" style={{ margin: 0 }}>{e.excerpt}</blockquote>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            )}
            {tab === 'sources' && (
              <Card>
                <CardTitle title="Where this was found" />
                <ul className="list-plain stack">
                  {v.source_links.map((s, i) => (
                    <li key={i} className="stack-sm">
                      <div className="row-between">
                        <strong>{s.source}</strong>
                        <Badge>{humanize(s.collection_method)}</Badge>
                      </div>
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="small wrap-anywhere row" style={{ gap: 4 }}>
                          <Link2 size={14} aria-hidden="true" /> {s.url}
                        </a>
                      )}
                      <span className="xs muted">First seen {fmtDate(s.first_seen_at, true)} · last seen {fmtRelative(s.last_seen_at)}{s.gone_at && ` · missing from listing since ${fmtDate(s.gone_at)}`}</span>
                      {s.raw_version_id && <RawLink id={s.raw_version_id} />}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        </div>
        <aside className="stack">
          <Card>
            <CardTitle title="Fit at a glance" as="h2" />
            <ScoreRow cfit={v.candidate_fit_score} pfit={v.preference_fit_score} conf={v.data_confidence} />
            <p className="xs muted" style={{ marginTop: 'var(--space-3)' }}>Transparent heuristics, not a prediction of hiring success.</p>
          </Card>
          <Card>
            <CardTitle title="Timeline" as="h2" />
            <dl className="kv">
              <dt>First seen</dt><dd>{fmtDate(v.first_seen_at, true)}</dd>
              <dt>Last seen</dt><dd>{fmtRelative(v.last_seen_at)}</dd>
              <dt>Last checked</dt><dd>{v.last_checked_at ? fmtRelative(v.last_checked_at) : 'Never'}</dd>
              <dt>Last verified</dt><dd>{v.last_verified_at ? fmtRelative(v.last_verified_at) : 'Not verified'}</dd>
              <dt>Published</dt><dd>{v.source_published_at ? fmtDate(v.source_published_at) : 'Unknown'}</dd>
            </dl>
          </Card>
          <Card>
            <div className="card-title">
              <h2 style={{ fontSize: 'var(--text-lg)' }} className="row"><History size={18} aria-hidden="true" /> Status history</h2>
              <Button size="sm" variant="ghost" onClick={() => setStatusOpen(true)}>Correct</Button>
            </div>
            <ul className="list-plain stack-sm">
              {v.history.map((h, i) => (
                <li key={i} className="small">
                  <strong>{humanize(h.to)}</strong> <span className="muted">· {humanize(h.actor)} · {fmtRelative(h.at)}</span>
                  {h.reason && <div className="xs muted">{h.reason}</div>}
                </li>
              ))}
            </ul>
          </Card>
          {v.duplicate_candidates.length > 0 && (
            <Alert tone="warning" title="Possible duplicates">
              {v.duplicate_candidates.map((d) => (
                <div key={d.id}>
                  <Link to={`/vacancies/${d.other_id}`}>Vacancy #{d.other_id}</Link> ({Math.round(d.score * 100)}% similar) — review in Import Center › Duplicates.
                </div>
              ))}
            </Alert>
          )}
          <Button variant="ghost" icon={<Flag size={16} />} onClick={() => setReportOpen(true)}>Report incorrect data</Button>
        </aside>
      </div>
      <StatusDialog open={statusOpen} onClose={() => setStatusOpen(false)} id={v.id} />
      <ReportDialog open={reportOpen} onClose={() => setReportOpen(false)} id={v.id} />
    </>
  )
}

function Fact({ k, v, origin }: { k: string; v: React.ReactNode; origin?: string }) {
  if (v === null || v === undefined || v === '') return null
  return (
    <>
      <dt>{k}</dt>
      <dd>
        {v}
        {origin && origin !== 'EXPLICIT' && <span className="xs muted"> ({humanize(origin)})</span>}
      </dd>
    </>
  )
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null
  return (
    <Card>
      <CardTitle title={title} />
      <ul className="stack-sm reading" style={{ margin: 0, paddingLeft: '1.2em' }}>
        {items.map((x, i) => <li key={i}>{x}</li>)}
      </ul>
    </Card>
  )
}

function FitPanel({ v }: { v: VacancyDetail }) {
  if (!v.match) return <Alert tone="info">No match analysis yet. Confirm your profile and set preferences to see a breakdown.</Alert>
  const b = v.match.breakdown
  const block = (title: string, comps: MatchComponent[], score: number | null) => (
    <Card>
      <div className="card-title">
        <h3>{title}</h3>
        <Meter value={score} label={title} />
      </div>
      <ul className="list-plain stack">
        {comps.map((c) => (
          <li key={c.name} className="stack-sm">
            <div className="row-between small">
              <strong>{humanize(c.name)}</strong>
              {c.score === null ? <Badge tone="outline">Unknown</Badge> : <span className="num">{Math.round(c.score * 100)}%</span>}
            </div>
            <span className="xs secondary">{c.detail}</span>
            {c.matched?.length > 0 && (
              <div className="chip-list">
                {c.matched.map((m, i) => <Badge key={i} tone="success">{m.skill ?? m.text}</Badge>)}
              </div>
            )}
            {c.missing?.length > 0 && (
              <div className="chip-list">
                {c.missing.map((m) => <Badge key={m} tone="danger">Missing: {m}</Badge>)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
  return (
    <>
      {block('Profile fit', b.candidate_fit, v.candidate_fit_score)}
      {block('Preference fit', b.preference_fit, v.preference_fit_score)}
      {b.unknowns.length > 0 && (
        <Alert tone="info" title="Unknown — excluded from the score">
          {b.unknowns.map(humanize).join(', ')}
        </Alert>
      )}
      <p className="xs muted"><ShieldCheck size={12} aria-hidden="true" style={{ display: 'inline' }} /> {b.note}</p>
    </>
  )
}

function RawLink({ id }: { id: number }) {
  const [open, setOpen] = useState(false)
  const q = useGet<{ text: string; collected_at: string; content_hash: string; truncated: boolean }>(['raw', id], open ? `/raw-versions/${id}` : null)
  return (
    <>
      <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={() => setOpen(true)}>View raw source snapshot</button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Raw source snapshot" description={q.data ? `Collected ${fmtDate(q.data.collected_at, true)} · sha256 ${q.data.content_hash.slice(0, 12)}…` : undefined}>
        {q.isLoading ? <LoadingCards count={1} /> : q.data && <pre className="raw">{q.data.text}</pre>}
        {q.data?.truncated && <Alert tone="warning">This snapshot was truncated at the size limit.</Alert>}
      </Dialog>
    </>
  )
}

function StatusDialog({ open, onClose, id }: { open: boolean; onClose: () => void; id: number }) {
  const [status, setStatus] = useState('VERIFIED_OPEN')
  const [reason, setReason] = useState('')
  const act = useAction(() => post(`/vacancies/${id}/status`, { status, reason }), { invalidate: [['vacancy', String(id)], ['vacancies']], success: 'Status updated', onSuccess: onClose })
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Correct vacancy status"
      description="Your correction is recorded in the history with you as the actor."
      actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={reason.length < 3} loading={act.isPending} onClick={() => act.mutate(undefined)}>Save</Button></>}
    >
      <Select label="Status" value={status} onChange={(e) => setStatus(e.target.value)} options={['VERIFIED_OPEN', 'LIKELY_OPEN', 'STATUS_UNKNOWN', 'CLOSED', 'EXPIRED', 'NEEDS_REVIEW', 'REJECTED_AS_IRRELEVANT'].map((s) => ({ value: s, label: humanize(s) }))} />
      <TextArea label="Reason" required value={reason} onChange={(e) => setReason(e.target.value)} hint="e.g. “Checked the company site on 12 Dec — still accepting applications.”" />
    </Dialog>
  )
}

function ReportDialog({ open, onClose, id }: { open: boolean; onClose: () => void; id: number }) {
  const [note, setNote] = useState('')
  const act = useAction(() => put(`/vacancies/${id}/saved`, { state: 'REPORTED', note }), { invalidate: [['vacancy', String(id)]], success: 'Thanks — noted for review', onSuccess: onClose })
  return (
    <Dialog open={open} onClose={onClose} title="Report incorrect data" actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" icon={<AlertTriangle size={16} />} disabled={!note} loading={act.isPending} onClick={() => act.mutate(undefined)}>Report</Button></>}>
      <TextArea label="What is wrong?" value={note} onChange={(e) => setNote(e.target.value)} />
    </Dialog>
  )
}
