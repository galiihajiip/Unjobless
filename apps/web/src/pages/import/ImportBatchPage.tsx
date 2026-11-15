import { ClipboardPaste, RotateCw } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ItemStatusBadge } from '@/components/domain/StatusBadge'
import { Alert, Badge, Button, Card, CardTitle, Dialog, ErrorState, LoadingCards, PageHeader, Select, TextInput } from '@/components/ui'
import { post } from '@/lib/api'
import { fmtRelative, humanize } from '@/lib/format'
import { useAction, useGet } from '@/lib/queries'
import type { Extraction, ImportBatch, ImportItem } from '@/lib/types'

const ACTIVE = new Set(['QUEUED', 'FETCHING', 'EXTRACTED'])

export default function ImportBatchPage() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const q = useGet<{ batch: ImportBatch; items: ImportItem[] }>(['batch', id], `/imports/batches/${id}`, {
    refetchInterval: (query) => ((query.state.data as { items: ImportItem[] } | undefined)?.items.some((i) => ACTIVE.has(i.status)) ?? true ? 3000 : false),
  })
  const selected = Number(sp.get('item')) || null
  if (q.isLoading) return <LoadingCards />
  if (q.error || !q.data) return <ErrorState error={q.error} />
  const { batch, items } = q.data
  const working = items.some((i) => ACTIVE.has(i.status))
  return (
    <>
      <PageHeader crumbs={[{ label: 'Import Center', to: '/import?tab=history' }, { label: `Batch #${batch.id}` }]} title={`Import batch #${batch.id}`} description={`${batch.item_count} item(s) · ${humanize(batch.status)}${working ? ' · processing…' : ''}`} />
      <div className="two-col">
        <div className="stack" aria-live="polite">
          {items.map((i) => (
            <Card key={i.id} className="stack-sm" style={{ outline: i.id === selected ? '2px solid var(--brand-300)' : undefined }}>
              <div className="row-between">
                <div className="row" style={{ gap: 6, minWidth: 0 }}>
                  <ItemStatusBadge value={i.status} />
                  {i.classification && <Badge tone="brand">{humanize(i.classification.primary)}</Badge>}
                </div>
                <span className="xs muted">{fmtRelative(i.updated_at)}</span>
              </div>
              <strong className="wrap-anywhere">{i.title ?? i.input_url ?? 'Pasted content'}</strong>
              {i.input_url && <a className="xs wrap-anywhere" href={i.input_url} target="_blank" rel="noopener noreferrer">{i.input_url}</a>}
              {i.detected_connector && <span className="xs muted">{i.detected_connector}</span>}
              {i.failure_reason && <Alert tone={i.status === 'DUPLICATE' ? 'info' : 'warning'}>{i.failure_reason}</Alert>}
              <div className="row">
                {i.status === 'NEEDS_REVIEW' && <Button size="sm" variant="primary" onClick={() => setSp({ item: String(i.id) })}>Review</Button>}
                {i.result_vacancy_id && <Link className="btn btn-sm btn-secondary" to={`/vacancies/${i.result_vacancy_id}`}>Open vacancy</Link>}
                {i.paste_fallback && <Link className="btn btn-sm btn-ghost" to="/import?tab=paste"><ClipboardPaste size={14} /> Paste instead</Link>}
                {i.paste_fallback && <RetryButton item={i} />}
              </div>
            </Card>
          ))}
        </div>
        <aside>{selected ? <ReviewPanel key={selected} itemId={selected} onDone={() => setSp({})} /> : <Card><p className="small secondary">Select an item marked “Needs review” to see its extracted fields, evidence and source text.</p></Card>}</aside>
      </div>
    </>
  )
}

function RetryButton({ item }: { item: ImportItem }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState(item.input_url ?? '')
  const act = useAction(() => post(`/imports/items/${item.id}/retry`, { corrected_url: url !== item.input_url ? url : null }), { invalidate: [['batch']], success: 'Queued again', onSuccess: () => setOpen(false) })
  if (!item.input_url) return null
  return (
    <>
      <Button size="sm" variant="ghost" icon={<RotateCw size={14} />} onClick={() => setOpen(true)}>Retry</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Retry import" actions={<><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="primary" loading={act.isPending} onClick={() => act.mutate(undefined)}>Retry</Button></>}>
        <TextInput label="URL" type="url" value={url} onChange={(e) => setUrl(e.target.value)} hint="Correct the link if needed. It is re-validated before fetching." />
      </Dialog>
    </>
  )
}

const FIELDS: { key: keyof Extraction; label: string; type?: 'text' | 'number' | 'date' | 'list' | 'select'; options?: string[] }[] = [
  { key: 'title', label: 'Title' },
  { key: 'company', label: 'Company' },
  { key: 'locations', label: 'Locations', type: 'list' },
  { key: 'employment_type', label: 'Employment type', type: 'select', options: ['UNKNOWN', 'INTERNSHIP', 'FULL_TIME', 'PART_TIME', 'CONTRACT', 'FREELANCE', 'TRAINEE', 'TEMPORARY', 'VOLUNTEER'] },
  { key: 'work_arrangement', label: 'Work arrangement', type: 'select', options: ['UNKNOWN', 'ONSITE', 'HYBRID', 'REMOTE', 'FLEXIBLE'] },
  { key: 'application_url', label: 'Application URL' },
  { key: 'application_email', label: 'Application email' },
  { key: 'application_deadline', label: 'Deadline', type: 'date' },
  { key: 'salary_min', label: 'Pay min', type: 'number' },
  { key: 'salary_max', label: 'Pay max', type: 'number' },
  { key: 'salary_currency', label: 'Currency' },
  { key: 'pay_period', label: 'Pay period', type: 'select', options: ['UNKNOWN', 'MONTH', 'YEAR', 'HOUR', 'DAY', 'WEEK', 'PROJECT'] },
  { key: 'required_skills', label: 'Required skills', type: 'list' },
  { key: 'preferred_skills', label: 'Preferred skills', type: 'list' },
  { key: 'min_gpa', label: 'Min GPA', type: 'number' },
  { key: 'min_semester', label: 'Min semester', type: 'number' },
]

function ReviewPanel({ itemId, onDone }: { itemId: number; onDone: () => void }) {
  const navigate = useNavigate()
  const q = useGet<ImportItem>(['import-item', itemId], `/imports/items/${itemId}`)
  const [corr, setCorr] = useState<Record<string, unknown>>({})
  const [mergeId, setMergeId] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const inv = [['batch'], ['review-queue'], ['import-item', itemId], ['vacancies']]
  const vacancy = useAction(() => post<{ vacancy_id: number }>(`/imports/items/${itemId}/confirm-vacancy`, { corrections: corr }), { invalidate: inv, success: 'Saved as a verified vacancy', onSuccess: (r) => navigate(`/vacancies/${r.vacancy_id}`) })
  const lead = useAction(() => post(`/imports/items/${itemId}/confirm-lead`), { invalidate: inv, success: 'Saved as an unverified lead', onSuccess: onDone })
  const reject = useAction(() => post(`/imports/items/${itemId}/reject`, {}), { invalidate: inv, success: 'Rejected', onSuccess: onDone })
  const merge = useAction(() => post(`/imports/items/${itemId}/merge`, { vacancy_id: Number(mergeId) }), { invalidate: inv, success: 'Merged into existing vacancy', onSuccess: onDone })
  if (q.isLoading || !q.data) return <LoadingCards count={1} />
  const it = q.data
  const x = it.extraction?.extraction
  const cls = it.extraction?.classification as { primary?: string; reason?: string; confidence?: number; ambiguity_flags?: string[] } | undefined
  const val = (k: string) => (k in corr ? corr[k] : x?.[k])
  return (
    <div className="stack">
      <Card className="stack-sm">
        <CardTitle title="Classification" as="h2" />
        {cls && <><Badge tone="brand">{humanize(cls.primary)}</Badge><span className="small secondary">{cls.reason}</span><span className="xs muted">Confidence {Math.round((cls.confidence ?? 0) * 100)}% — this is not verification.</span></>}
        {cls?.ambiguity_flags?.length ? <div className="chip-list">{cls.ambiguity_flags.map((f) => <Badge key={f} tone="warning">{humanize(f)}</Badge>)}</div> : null}
        {it.media?.map((m) => <Alert key={m.id} tone={m.status === 'SUCCEEDED' ? 'success' : 'info'}>Media ({m.mime}): {humanize(m.status)}{m.message ? ` — ${m.message}` : ''}</Alert>)}
      </Card>
      {x ? (
        <Card className="stack-sm">
          <CardTitle title="Extracted fields" as="h2" />
          <span className="xs muted">Edit anything that is wrong. Edited values are recorded as your corrections.</span>
          {FIELDS.map((f) => {
            const v = val(f.key as string)
            const ev = x.evidence.find((e) => e.field === f.key || (f.key === 'salary_min' && e.field === 'salary'))
            const common = { label: f.label, hint: ev ? `${humanize(ev.origin)}: “${ev.excerpt.slice(0, 120)}”` : v == null || (Array.isArray(v) && !v.length) ? 'Not stated in the source' : undefined }
            if (f.type === 'select') return <Select key={f.key as string} {...common} value={String(v ?? 'UNKNOWN')} onChange={(e) => setCorr({ ...corr, [f.key]: e.target.value })} options={(f.options ?? []).map((o) => ({ value: o, label: humanize(o) }))} />
            if (f.type === 'list') return <TextInput key={f.key as string} {...common} value={((v as string[]) ?? []).join(', ')} onChange={(e) => setCorr({ ...corr, [f.key]: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
            return <TextInput key={f.key as string} {...common} type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'} value={v == null ? '' : String(v)} onChange={(e) => setCorr({ ...corr, [f.key]: e.target.value === '' ? null : f.type === 'number' ? Number(e.target.value) : e.target.value })} />
          })}
          {x.warnings.length > 0 && <Alert tone="warning">{x.warnings.join(' ')}</Alert>}
        </Card>
      ) : <Alert tone="info">This looks like an informal post rather than a vacancy, so no vacancy fields were extracted. You can still save it as a lead.</Alert>}
      <Card className="stack-sm">
        <Button variant="ghost" size="sm" onClick={() => setShowRaw((s) => !s)}>{showRaw ? 'Hide' : 'Show'} source text</Button>
        {showRaw && it.raw && <pre className="raw">{it.raw.text}</pre>}
        {showRaw && it.transcriptions?.map((t, i) => <div key={i}><span className="xs muted">{humanize(t.kind)} · {humanize(t.origin)}</span><pre className="raw">{t.text}</pre></div>)}
      </Card>
      <Card className="stack-sm">
        <CardTitle title="Decision" as="h2" />
        <Button variant="primary" loading={vacancy.isPending} onClick={() => vacancy.mutate(undefined)} disabled={!val('title')}>I checked it — save as vacancy</Button>
        <Button loading={lead.isPending} onClick={() => lead.mutate(undefined)}>Save as unverified lead</Button>
        <div className="row" style={{ flexWrap: 'nowrap' }}>
          <TextInput label="Merge into vacancy #" type="number" value={mergeId} onChange={(e) => setMergeId(e.target.value)} />
          <Button style={{ alignSelf: 'flex-end' }} disabled={!mergeId} loading={merge.isPending} onClick={() => merge.mutate(undefined)}>Merge</Button>
        </div>
        <Button variant="danger" loading={reject.isPending} onClick={() => reject.mutate(undefined)}>Reject as irrelevant</Button>
      </Card>
    </div>
  )
}
