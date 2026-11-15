import { useQuery } from '@tanstack/react-query'
import { ClipboardPaste, Copy, Download, FileImage, Link2 } from 'lucide-react'
import { useDeferredValue, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { ItemStatusBadge } from '@/components/domain/StatusBadge'
import { Alert, Badge, Button, Card, CardTitle, EmptyState, ErrorState, LoadingCards, PageHeader, Select, Tabs, TextArea, TextInput } from '@/components/ui'
import { api, post } from '@/lib/api'
import { fmtRelative, humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'
import type { ImportBatch, ImportItem, Paged } from '@/lib/types'

type Tab = 'urls' | 'paste' | 'upload' | 'review' | 'history' | 'duplicates'
interface LineCheck { line: number; raw: string; ok: boolean; url: string | null; domain: string | null; detected: string | null; error: string | null }

export default function ImportPage() {
  const [sp, setSp] = useSearchParams()
  const tab = (sp.get('tab') as Tab) ?? 'urls'
  const review = useGet<ImportItem[]>(['review-queue'], '/imports/review-queue')
  return (
    <>
      <PageHeader title="Import Center" description="Bring in opportunities from links, copied posts, posters and PDFs. Everything waits for your review before it is saved." />
      <Tabs<Tab> label="Import methods" idPrefix="imp" value={tab} onChange={(t) => setSp({ tab: t })} items={[
        { value: 'urls', label: 'URLs' }, { value: 'paste', label: 'Paste content' }, { value: 'upload', label: 'Poster / PDF' },
        { value: 'review', label: 'Review', count: review.data?.length }, { value: 'history', label: 'History' }, { value: 'duplicates', label: 'Duplicates' },
      ]} />
      <div id="imp-panel" role="tabpanel" style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'urls' && <UrlTab />}
        {tab === 'paste' && <PasteTab />}
        {tab === 'upload' && <UploadTab />}
        {tab === 'review' && <ReviewQueue items={review.data} loading={review.isLoading} />}
        {tab === 'history' && <HistoryTab />}
        {tab === 'duplicates' && <DuplicatesTab />}
      </div>
    </>
  )
}

function UrlTab() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [note, setNote] = useState('')
  const [hint, setHint] = useState('')
  const deferred = useDeferredValue(text)
  const check = useQuery({
    queryKey: ['url-check', deferred],
    queryFn: () => post<{ lines: LineCheck[]; valid: number; max: number }>('/imports/urls/check', { text: deferred }),
    enabled: deferred.trim().length > 0,
    staleTime: 60_000,
  })
  const submit = useAction(() => post<{ batch: ImportBatch }>('/imports/urls', { text, note: note || null, category_hint: hint || null }), {
    invalidate: [['batches']],
    success: 'Batch queued',
    onSuccess: (r) => navigate(`/import/batches/${r.batch.id}`),
  })
  const lines = check.data?.lines ?? []
  return (
    <div className="two-col">
      <Card className="stack">
        <TextArea label="Links, one per line" className="mono" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={'https://careers.example.com/jobs/123\nhttps://jobs.lever.co/company/abc'} hint="Each link is fetched safely in the background. Login-only pages (e.g. most social media) cannot be fetched — use Paste content for those." />
        <div className="grid grid-2">
          <TextInput label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Select label="Category hint (optional)" value={hint} onChange={(e) => setHint(e.target.value)} options={[{ value: '', label: 'Let Unjobless decide' }, { value: 'vacancy', label: 'Job / internship vacancy' }, { value: 'lead', label: 'Informal lead / referral' }, { value: 'program', label: 'Program / campaign' }]} />
        </div>
        {submit.error && <Alert tone="danger">{errorMessage(submit.error)}</Alert>}
        <Button variant="primary" icon={<Link2 size={16} />} disabled={!check.data?.valid} loading={submit.isPending} onClick={() => submit.mutate(undefined)}>
          Import {check.data?.valid ? `${check.data.valid} link${check.data.valid === 1 ? '' : 's'}` : ''}
        </Button>
      </Card>
      <Card>
        <CardTitle title="Check" as="h2" />
        {lines.length === 0 ? <p className="small secondary">Paste links to see which will be imported.</p> : (
          <ul className="list-plain stack-sm">
            {lines.map((l) => (
              <li key={l.line} className="small stack-sm" style={{ gap: 2 }}>
                <span className="row" style={{ gap: 6 }}>
                  <Badge tone={l.ok ? 'success' : 'danger'}>{l.ok ? 'OK' : 'Skip'}</Badge>
                  <span className="truncate" style={{ maxWidth: 220 }}>{l.domain ?? l.raw}</span>
                </span>
                {l.detected && <span className="xs muted">{l.detected}</span>}
                {l.error && <span className="xs" style={{ color: 'var(--danger)' }}>{l.error}</span>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function PasteTab() {
  const navigate = useNavigate()
  const [f, setF] = useState({ text: '', source_url: '', platform: '', author_label: '', published_at: '', content_type_hint: '', notes: '', extra_text: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const submit = useAction(() => post<{ batch: ImportBatch }>('/imports/paste', {
    records: [{ ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v || null])), text: f.text, published_at: f.published_at ? new Date(f.published_at).toISOString() : null }],
  }), { invalidate: [['batches'], ['review-queue']], success: 'Saved exactly as pasted — analysing', onSuccess: (r) => navigate(`/import/batches/${r.batch.id}`) })
  return (
    <Card className="stack">
      <TextArea label="Pasted content" rows={10} value={f.text} onChange={set('text')} hint="The text is stored exactly as pasted. Only paste content you are allowed to use." required />
      <div className="grid grid-2">
        <TextInput label="Source URL (optional)" type="url" value={f.source_url} onChange={set('source_url')} />
        <TextInput label="Platform (optional)" value={f.platform} onChange={set('platform')} placeholder="Instagram, LinkedIn, email, WhatsApp group…" />
        <TextInput label="Public account / author label (optional)" value={f.author_label} onChange={set('author_label')} hint="Only for public organisation or public accounts." />
        <TextInput label="Posted on (optional)" type="date" value={f.published_at} onChange={set('published_at')} />
        <Select label="Content type hint (optional)" value={f.content_type_hint} onChange={set('content_type_hint')} options={[{ value: '', label: 'Auto-detect' }, { value: 'job_post', label: 'Job post' }, { value: 'social_post', label: 'Social post' }, { value: 'email', label: 'Email' }, { value: 'announcement', label: 'Announcement' }, { value: 'transcript', label: 'Transcript' }]} />
        <TextInput label="Notes (optional)" value={f.notes} onChange={set('notes')} />
      </div>
      <TextArea label="OCR or transcript text you have (optional)" rows={4} value={f.extra_text} onChange={set('extra_text')} />
      {submit.error && <Alert tone="danger">{errorMessage(submit.error)}</Alert>}
      <Button variant="primary" icon={<ClipboardPaste size={16} />} disabled={!f.text.trim()} loading={submit.isPending} onClick={() => submit.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Analyse pasted content</Button>
    </Card>
  )
}

function UploadTab() {
  const navigate = useNavigate()
  const ref = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [notes, setNotes] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  return (
    <Card className="stack">
      <p className="secondary small">Upload a poster, screenshot, PDF or caption file (.vtt/.srt) you are authorised to process. Text is extracted with OCR where available; you can always add the text manually below.</p>
      <div className="row">
        <Button icon={<FileImage size={16} />} onClick={() => ref.current?.click()}>{file ? file.name : 'Choose file'}</Button>
        <input ref={ref} hidden type="file" aria-label="File to import" accept="image/png,image/jpeg,image/webp,application/pdf,.vtt,.srt,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      <TextInput label="Source URL (optional)" type="url" value={url} onChange={(e) => setUrl(e.target.value)} />
      <TextArea label="Text from the poster (optional, used if OCR is unavailable)" value={notes} onChange={(e) => setNotes(e.target.value)} />
      {err && <Alert tone="danger">{err}</Alert>}
      <Button variant="primary" disabled={!file} loading={busy} style={{ alignSelf: 'flex-start' }} onClick={async () => {
        if (!file) return
        setBusy(true)
        setErr(null)
        try {
          const fd = new FormData()
          fd.append('file', file)
          if (url) fd.append('source_url', url)
          if (notes) fd.append('extra_text', notes)
          const r = await api<{ batch: ImportBatch }>('/imports/upload', { method: 'POST', body: fd })
          navigate(`/import/batches/${r.batch.id}`)
        } catch (x) {
          setErr(errorMessage(x))
        } finally {
          setBusy(false)
        }
      }}>Upload & analyse</Button>
    </Card>
  )
}

function ReviewQueue({ items, loading }: { items?: ImportItem[]; loading: boolean }) {
  if (loading) return <LoadingCards />
  if (!items?.length) return <EmptyState icon={<Download size={28} />} title="Nothing to review">Imported items that are ready for your decision appear here.</EmptyState>
  return (
    <div className="stack">
      {items.map((i) => (
        <Link key={i.id} to={`/import/batches/${i.batch_id}?item=${i.id}`} className="card card-link row-between">
          <div className="stack-sm" style={{ minWidth: 0 }}>
            <strong className="truncate">{i.title ?? i.input_url ?? 'Pasted content'}</strong>
            <span className="xs muted">{i.detected_domain ?? i.paste_meta?.platform ?? 'paste'} · {fmtRelative(i.updated_at)}</span>
          </div>
          {i.classification && <Badge tone="brand">{humanize(i.classification.primary)}</Badge>}
        </Link>
      ))}
    </div>
  )
}

function HistoryTab() {
  const q = useGet<Paged<ImportBatch>>(['batches'], '/imports/batches?limit=50')
  if (q.isLoading) return <LoadingCards />
  if (q.error) return <ErrorState error={q.error} />
  if (!q.data?.items.length) return <EmptyState icon={<Copy size={28} />} title="No imports yet" />
  return (
    <div className="stack">
      {q.data.items.map((b) => (
        <Link key={b.id} to={`/import/batches/${b.id}`} className="card card-link row-between">
          <div className="stack-sm">
            <strong>{b.kind === 'URL' ? 'URL batch' : 'Paste / upload'} #{b.id}</strong>
            <span className="xs muted">{b.item_count} item{b.item_count === 1 ? '' : 's'} · {fmtRelative(b.created_at)}{b.note ? ` · ${b.note}` : ''}</span>
          </div>
          <div className="row" style={{ gap: 4 }}>
            {Object.entries(b.counts).map(([k, n]) => <span key={k} className="row" style={{ gap: 2 }}><ItemStatusBadge value={k} /><span className="xs num">{n}</span></span>)}
          </div>
        </Link>
      ))}
    </div>
  )
}

interface Dup { id: number; score: number; signals: Record<string, unknown>; a: { id: number; title: string; company: string | null; location: string | null; url: string | null }; b: Dup['a'] }

function DuplicatesTab() {
  const q = useGet<Dup[]>(['dedup'], '/dedup/candidates')
  const decide = useAction(({ id, action, keep }: { id: number; action: string; keep?: number }) => post(`/dedup/candidates/${id}`, { action, keep_id: keep }), { invalidate: [['dedup'], ['vacancies']], success: 'Decision saved (undo is available in the audit log)' })
  if (q.isLoading) return <LoadingCards />
  if (!q.data?.length) return <EmptyState icon={<Copy size={28} />} title="No possible duplicates">Pairs that look alike but could not be merged automatically appear here.</EmptyState>
  return (
    <div className="stack">
      {q.data.map((d) => (
        <Card key={d.id} className="stack">
          <div className="row-between"><strong>{Math.round(d.score * 100)}% similar</strong>{Array.isArray(d.signals.blockers) && (d.signals.blockers as string[]).length > 0 && <Badge tone="warning">{(d.signals.blockers as string[]).map(humanize).join(', ')}</Badge>}</div>
          <div className="grid grid-2">
            {[d.a, d.b].map((v) => (
              <Card key={v.id} tone="soft" className="stack-sm">
                <Link to={`/vacancies/${v.id}`}><strong>{v.title}</strong></Link>
                <span className="small secondary">{v.company ?? '—'} · {v.location ?? '—'}</span>
                <Button size="sm" onClick={() => decide.mutate({ id: d.id, action: 'merge', keep: v.id })}>Merge, keep this one</Button>
              </Card>
            ))}
          </div>
          <Button variant="ghost" size="sm" style={{ alignSelf: 'flex-start' }} onClick={() => decide.mutate({ id: d.id, action: 'reject' })}>They are different vacancies</Button>
        </Card>
      ))}
    </div>
  )
}
