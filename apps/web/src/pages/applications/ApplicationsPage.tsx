import { BriefcaseBusiness, CalendarClock, FileText } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Alert, Badge, Button, Card, Checkbox, Dialog, EmptyState, ErrorState, LoadingCards, PageHeader, Select, Tabs, TextArea, TextInput } from '@/components/ui'
import { patch, post, qs } from '@/lib/api'
import { fmtDate, fmtRelative, humanize } from '@/lib/format'
import { useAction, useGet } from '@/lib/queries'
import type { Application } from '@/lib/types'

const STATUSES = ['SAVED', 'SHORTLISTED', 'PREPARING', 'APPLIED', 'ASSESSMENT', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN', 'ARCHIVED']
type View = 'active' | 'applied' | 'closed' | 'all'
const VIEWS: Record<View, string[]> = {
  active: ['SAVED', 'SHORTLISTED', 'PREPARING'],
  applied: ['APPLIED', 'ASSESSMENT', 'INTERVIEW', 'OFFER'],
  closed: ['REJECTED', 'WITHDRAWN', 'ARCHIVED'],
  all: [],
}

export default function ApplicationsPage() {
  const [view, setView] = useState<View>('active')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const list = useGet<Application[]>(['applications', view, q], `/applications${qs({ status: VIEWS[view], q })}`)
  const due = useGet<Application[]>(['applications', 'due'], '/applications?due_within_days=7')
  return (
    <>
      <PageHeader title="Applications" description="Track what you are preparing and where you applied. Unjobless never submits applications for you." />
      {(due.data?.length ?? 0) > 0 && (
        <Alert tone="warning" title="Due in the next 7 days">
          {due.data!.map((a) => `${a.vacancy?.title ?? 'Vacancy'} (${a.deadline ? `deadline ${fmtDate(a.deadline)}` : `follow up ${fmtDate(a.follow_up_at)}`})`).join(' · ')}
        </Alert>
      )}
      <div className="row-between" style={{ margin: 'var(--space-4) 0' }}>
        <Tabs<View> label="Application view" idPrefix="apps" value={view} onChange={setView} items={[{ value: 'active', label: 'Preparing' }, { value: 'applied', label: 'In progress' }, { value: 'closed', label: 'Closed' }, { value: 'all', label: 'All' }]} />
        <input aria-label="Search applications" className="input" style={{ maxWidth: 280 }} placeholder="Search title, company, notes" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div id="apps-panel" role="tabpanel" className="stack">
        {list.isLoading ? <LoadingCards /> : list.error ? <ErrorState error={list.error} /> : !list.data?.length ? (
          <EmptyState icon={<BriefcaseBusiness size={28} />} title="Nothing here yet" action={<Link className="btn btn-primary" to="/discover">Find vacancies</Link>}>Use “Track” on a vacancy to add it.</EmptyState>
        ) : (
          list.data.map((a) => (
            <Card key={a.id} className="row-between" style={{ alignItems: 'flex-start' }}>
              <div className="stack-sm" style={{ minWidth: 0 }}>
                <div className="row" style={{ gap: 6 }}>
                  <Badge tone={['OFFER'].includes(a.status) ? 'success' : ['REJECTED', 'WITHDRAWN'].includes(a.status) ? 'danger' : ['APPLIED', 'ASSESSMENT', 'INTERVIEW'].includes(a.status) ? 'info' : 'neutral'} dot>{humanize(a.status)}</Badge>
                  {a.vacancy && a.vacancy.status !== 'VERIFIED_OPEN' && <Badge tone="outline">Vacancy {humanize(a.vacancy.status)}</Badge>}
                </div>
                <h3><Link to={`/vacancies/${a.vacancy_id}`} style={{ color: 'inherit' }}>{a.vacancy?.title}</Link></h3>
                <span className="small secondary">{a.vacancy?.company ?? 'Company not stated'}</span>
                <span className="xs muted row" style={{ gap: 4 }}>
                  <CalendarClock size={12} aria-hidden="true" />
                  {a.applied_at ? `Applied ${fmtDate(a.applied_at)}` : 'Not applied yet'}
                  {a.deadline && ` · deadline ${fmtDate(a.deadline)}`}
                  {a.follow_up_at && ` · follow up ${fmtDate(a.follow_up_at)}`} · updated {fmtRelative(a.updated_at)}
                </span>
              </div>
              <div className="row">
                <Link className="btn btn-ai btn-sm" to={`/applications/tailor/${a.vacancy_id}`}><FileText size={14} /> Documents</Link>
                <Button size="sm" onClick={() => setOpen(a.id)}>Update</Button>
              </div>
            </Card>
          ))
        )}
      </div>
      {open && <AppDialog id={open} onClose={() => setOpen(null)} />}
    </>
  )
}

function AppDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const q = useGet<Application>(['application', id], `/applications/by-id/${id}`)
  const [status, setStatus] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [force, setForce] = useState(false)
  const [fields, setFields] = useState<Partial<Application>>({})
  const setSt = useAction(() => post(`/applications/by-id/${id}/status`, { status, note: note || null, force }), { invalidate: [['applications'], ['application', id]], success: 'Status updated', onSuccess: () => { setStatus(null); setNote('') } })
  const save = useAction(() => patch(`/applications/by-id/${id}`, fields), { invalidate: [['applications'], ['application', id]], success: 'Saved', onSuccess: onClose })
  const a = q.data
  return (
    <Dialog open onClose={onClose} title={a?.vacancy?.title ?? 'Application'} description={a?.vacancy?.company ?? undefined} actions={<><Button onClick={onClose}>Close</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)}>Save details</Button></>}>
      {!a ? <LoadingCards count={1} /> : (
        <div className="stack">
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <Select label={`Status (now ${humanize(a.status)})`} value={status ?? a.status} onChange={(e) => setStatus(e.target.value)} options={STATUSES.map((s) => ({ value: s, label: humanize(s) }))} />
            </div>
            <Button variant="secondary" disabled={!status || status === a.status} loading={setSt.isPending} onClick={() => setSt.mutate(undefined)}>Change</Button>
          </div>
          {status === 'APPLIED' && <span className="xs muted">Mark as applied only after you submitted on the original site.</span>}
          <TextInput label="Note for this change (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Checkbox label="This is a correction (allow any status change)" checked={force} onChange={(e) => setForce(e.target.checked)} />
          <div className="grid grid-2">
            <TextInput label="Deadline" type="date" defaultValue={a.deadline ?? ''} onChange={(e) => setFields({ ...fields, deadline: e.target.value || null })} />
            <TextInput label="Follow-up date" type="date" defaultValue={a.follow_up_at ?? ''} onChange={(e) => setFields({ ...fields, follow_up_at: e.target.value || null })} />
            <TextInput label="Applied on" type="date" defaultValue={a.applied_at ?? ''} onChange={(e) => setFields({ ...fields, applied_at: e.target.value || null })} />
          </div>
          <TextArea label="Notes" defaultValue={a.notes ?? ''} onChange={(e) => setFields({ ...fields, notes: e.target.value })} />
          <TextArea label="Contact / interview notes" hint="Only what you enter yourself." defaultValue={a.contact_notes ?? ''} onChange={(e) => setFields({ ...fields, contact_notes: e.target.value })} />
          <div>
            <h3 style={{ fontSize: 'var(--text-md)', marginBottom: 'var(--space-2)' }}>Timeline</h3>
            <ul className="list-plain stack-sm">
              {a.history?.map((h, i) => <li key={i} className="small"><strong>{humanize(h.to)}</strong> <span className="muted">· {fmtDate(h.at, true)}</span>{h.note && <div className="xs muted">{h.note}</div>}</li>)}
            </ul>
          </div>
        </div>
      )}
    </Dialog>
  )
}
