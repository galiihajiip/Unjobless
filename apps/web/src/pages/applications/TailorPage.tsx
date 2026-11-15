import { AlertTriangle, Check, Download, FileText, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { Alert, Badge, Button, Card, CardTitle, EmptyState, ErrorState, LoadingCards, PageHeader, Select, Tabs, TextArea } from '@/components/ui'
import { post } from '@/lib/api'
import { fmtRelative, humanize } from '@/lib/format'
import { useAction, useGet } from '@/lib/queries'
import type { Claim, Tailored, VacancyDetail } from '@/lib/types'

type Tab = 'claims' | 'preview' | 'letter'

export default function TailorPage() {
  const { vacancyId } = useParams()
  const vac = useGet<VacancyDetail>(['vacancy', vacancyId], `/vacancies/${vacancyId}`)
  const versions = useGet<{ id: number; parent_id: number | null; finalized: boolean; created_at: string; method: string; language: string }[]>(['tailored', vacancyId], `/vacancies/${vacancyId}/tailored`)
  const [current, setCurrent] = useState<number | null>(null)
  const [lang, setLang] = useState<'id' | 'en'>('id')
  const [tab, setTab] = useState<Tab>('claims')
  const activeId = current ?? versions.data?.[0]?.id ?? null
  const tr = useGet<Tailored>(['tailored-one', activeId], activeId ? `/tailored/${activeId}` : null)
  const generate = useAction(() => post<Tailored>(`/vacancies/${vacancyId}/tailor`, { language: lang, use_ai: true }), {
    invalidate: [['tailored', vacancyId]],
    success: 'Draft generated — review each change',
    onSuccess: (t) => setCurrent(t.id),
  })
  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Applications', to: '/applications' }, { label: 'Tailor' }]}
        title="Tailor your application"
        description={vac.data ? `${vac.data.title} · ${vac.data.company ?? 'Company not stated'}` : undefined}
        actions={
          <>
            <Select label="Language" value={lang} onChange={(e) => setLang(e.target.value as 'id' | 'en')} options={[{ value: 'id', label: 'Bahasa Indonesia' }, { value: 'en', label: 'English' }]} />
            <Button variant="primary" icon={<Sparkles size={16} />} loading={generate.isPending} onClick={() => generate.mutate(undefined)} style={{ alignSelf: 'flex-end' }}>New tailored draft</Button>
          </>
        }
      />
      <Alert tone="info">Tailoring only reorders and rephrases facts from your confirmed profile. Changes that add numbers, skills or tools are flagged and stay rejected unless you confirm them. Your master CV is never changed.</Alert>
      {generate.error && <Alert tone="danger">{String((generate.error as Error).message)} {(generate.error as Error).message.includes('profile') && <Link to="/profile">Go to profile</Link>}</Alert>}
      <div style={{ marginTop: 'var(--space-4)' }}>
        {versions.isLoading ? <LoadingCards /> : !versions.data?.length ? (
          <EmptyState icon={<FileText size={28} />} title="No tailored version yet">Generate a draft to see suggested ordering, wording and missing requirements.</EmptyState>
        ) : (
          <div className="two-col">
            <div className="stack">
              <Tabs<Tab> label="Tailoring sections" idPrefix="tl" value={tab} onChange={setTab} items={[{ value: 'claims', label: 'Review changes' }, { value: 'preview', label: 'Preview & export' }, { value: 'letter', label: 'Cover letter' }]} />
              <div id="tl-panel" role="tabpanel">
                {tr.isLoading || !tr.data ? <LoadingCards count={2} /> : tr.error ? <ErrorState error={tr.error} /> : (
                  <>
                    {tab === 'claims' && <ClaimsReview t={tr.data} onNewVersion={setCurrent} />}
                    {tab === 'preview' && <Preview t={tr.data} onNewVersion={setCurrent} />}
                    {tab === 'letter' && <Letter vacancyId={Number(vacancyId)} lang={lang} tailoredId={tr.data.id} />}
                  </>
                )}
              </div>
            </div>
            <aside className="stack">
              {tr.data && (
                <Card>
                  <CardTitle title="Gaps" as="h2" />
                  {tr.data.content.missing_requirements.length ? (
                    <>
                      <div className="chip-list">{tr.data.content.missing_requirements.map((m) => <Badge key={m} tone="danger">{m}</Badge>)}</div>
                      <p className="xs muted" style={{ marginTop: 'var(--space-2)' }}>Not shown in your profile. Do not claim these unless you add evidence to your profile.</p>
                    </>
                  ) : <p className="small secondary">No missing required skills detected.</p>}
                  {tr.data.content.ai_note && <p className="xs muted">{tr.data.content.ai_note}</p>}
                </Card>
              )}
              <Card>
                <CardTitle title="Versions" as="h2" />
                <ul className="list-plain stack-sm">
                  {versions.data.map((v) => (
                    <li key={v.id}>
                      <button className={`btn btn-sm ${v.id === activeId ? 'btn-secondary' : 'btn-ghost'}`} style={{ width: '100%', justifyContent: 'space-between' }} onClick={() => setCurrent(v.id)} aria-current={v.id === activeId}>
                        <span>#{v.id} {v.parent_id ? `(from #${v.parent_id})` : ''} {v.finalized && '· final'}</span>
                        <span className="muted xs">{v.language.toUpperCase()} · {fmtRelative(v.created_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            </aside>
          </div>
        )}
      </div>
    </>
  )
}

function ClaimsReview({ t, onNewVersion }: { t: Tailored; onNewVersion: (id: number) => void }) {
  const [decisions, setDecisions] = useState<Record<string, boolean | null>>({})
  const [edits, setEdits] = useState<Record<string, string>>({})
  const save = useAction((finalize: boolean) => post<Tailored>(`/tailored/${t.id}/decisions`, { decisions, edits, finalize }), {
    invalidate: [['tailored']],
    success: 'Saved as a new version',
    onSuccess: (n) => { setDecisions({}); setEdits({}); onNewVersion(n.id) },
  })
  const claims = t.content.claims
  if (!claims.length) return <Card><p className="secondary">No wording changes proposed — only ordering. Check the preview.</p></Card>
  return (
    <div className="stack">
      {claims.map((c) => <ClaimCard key={c.id} c={c} decision={c.id in decisions ? (decisions[c.id] ?? null) : c.accepted} edit={edits[c.id]} onDecide={(v, confirmIssues) => setDecisions({ ...decisions, [c.id]: v, ...(confirmIssues ? { [`${c.id}:confirm_issues`]: true } : {}) })} onEdit={(txt) => setEdits({ ...edits, [c.id]: txt })} />)}
      <div className="row">
        <Button variant="primary" loading={save.isPending} disabled={!Object.keys(decisions).length && !Object.keys(edits).length} onClick={() => save.mutate(false)}>Save decisions</Button>
        <Button loading={save.isPending} onClick={() => save.mutate(true)}>Save & mark final</Button>
      </div>
    </div>
  )
}

function ClaimCard({ c, decision, edit, onDecide, onEdit }: { c: Claim; decision: boolean | null; edit?: string; onDecide: (v: boolean | null, confirmIssues?: boolean) => void; onEdit: (t: string) => void }) {
  const [editing, setEditing] = useState(false)
  const flagged = c.issues.length > 0
  return (
    <Card className="stack-sm" style={{ borderLeft: flagged ? '4px solid var(--warning)' : undefined }}>
      <div className="row-between">
        <div className="row" style={{ gap: 6 }}>
          <Badge>{humanize(c.section)}</Badge>
          <Badge tone={decision === true ? 'success' : decision === false ? 'danger' : 'outline'}>{decision === true ? 'Accepted' : decision === false ? 'Rejected' : 'Undecided'}</Badge>
          {c.edited_by_owner && <Badge tone="info">Edited by you</Badge>}
        </div>
        <span className="xs muted">Based on {c.fact_ids.length} profile fact{c.fact_ids.length === 1 ? '' : 's'}</span>
      </div>
      {c.original && <div className="stack-sm"><span className="xs muted">Before</span><p className="small secondary reading" style={{ textDecoration: c.original !== c.proposed ? 'line-through' : undefined }}>{c.original}</p></div>}
      <div className="stack-sm"><span className="xs muted">{c.original ? 'After' : 'Proposed'}</span><p className="reading">{edit ?? c.proposed}</p></div>
      {flagged && <Alert tone="warning" title="Needs your confirmation">{c.issues.join(' ')}</Alert>}
      {editing && <TextArea label="Edit wording" defaultValue={edit ?? c.proposed} onChange={(e) => onEdit(e.target.value)} hint="Edits are re-checked against your profile facts." />}
      <div className="row">
        <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={() => onDecide(true, flagged)}>{flagged ? 'Accept anyway' : 'Accept'}</Button>
        <Button size="sm" variant="ghost" icon={<X size={14} />} onClick={() => onDecide(false)}>Reject</Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing((e) => !e)}>{editing ? 'Done editing' : 'Edit'}</Button>
        {flagged && <span className="xs muted row" style={{ gap: 4 }}><AlertTriangle size={12} aria-hidden="true" /> Only accept if it is true.</span>}
      </div>
    </Card>
  )
}

function Preview({ t, onNewVersion }: { t: Tailored; onNewVersion: (id: number) => void }) {
  const [template, setTemplate] = useState(t.template ?? 'ats_classic')
  const exp = useAction((format: 'pdf' | 'docx') => post<{ id: number; filename: string }>(`/tailored/${t.id}/export`, { format, template }), {
    invalidate: [['tailored-one', t.id]],
    onSuccess: (r) => { window.location.href = `/api/exports/${r.id}` },
  })
  void onNewVersion
  const modern = template === 'modern_professional'
  return (
    <div className="stack">
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <Select label="Template" value={template} onChange={(e) => setTemplate(e.target.value)} options={[{ value: 'ats_classic', label: 'ATS Classic (single column, plain)' }, { value: 'modern_professional', label: 'Modern Professional' }]} />
        <Button variant="primary" icon={<Download size={16} />} loading={exp.isPending} onClick={() => exp.mutate('pdf')}>Download PDF</Button>
        <Button icon={<Download size={16} />} loading={exp.isPending} onClick={() => exp.mutate('docx')}>Download DOCX</Button>
      </div>
      <Card style={{ background: '#fff', fontFamily: 'Calibri, Carlito, var(--font-sans)', padding: 'var(--space-6)' }} aria-label="CV preview">
        <h2 style={{ fontSize: modern ? 26 : 22, color: modern ? 'var(--brand-700)' : 'inherit' }}>{t.preview.contact.full_name}</h2>
        {t.preview.headline && <p style={{ fontStyle: modern ? 'italic' : undefined }}>{t.preview.headline}</p>}
        <p className="small secondary wrap-anywhere">{[t.preview.contact.email, t.preview.contact.phone, t.preview.contact.location, ...t.preview.links.slice(0, 3)].filter(Boolean).join(' · ')}</p>
        {t.sections.map((s) => (
          <section key={s.title} style={{ marginTop: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 15, textTransform: modern ? 'none' : 'uppercase', color: modern ? 'var(--brand-700)' : 'inherit', borderBottom: modern ? '1px solid var(--brand-200)' : undefined, paddingBottom: 2 }}>{s.title}</h3>
            {s.items.map((it, i) => (
              <div key={i} style={{ marginTop: 6 }}>
                {it.title && <strong>{it.title}</strong>}
                {it.meta && <div className="small secondary">{it.meta}</div>}
                {it.text && <p className="small">{it.text}</p>}
                {it.bullets && it.bullets.length > 0 && <ul className="small" style={{ margin: '4px 0', paddingLeft: '1.2em' }}>{it.bullets.map((b, j) => <li key={j}>{b}</li>)}</ul>}
              </div>
            ))}
          </section>
        ))}
      </Card>
      {t.exports.length > 0 && (
        <Card>
          <CardTitle title="Exported files" />
          <ul className="list-plain stack-sm">{t.exports.map((e) => <li key={e.id} className="small"><a href={`/api/exports/${e.id}`}>{e.filename}</a> <span className="muted">· {humanize(e.template)} · {fmtRelative(e.created_at)}</span></li>)}</ul>
        </Card>
      )}
    </div>
  )
}

function Letter({ vacancyId, lang, tailoredId }: { vacancyId: number; lang: 'id' | 'en'; tailoredId: number }) {
  const list = useGet<{ id: number; body: string; claims: { sentence: string; fact_ids: string[]; issues: string[] }[]; language: string; created_at: string }[]>(['letters', vacancyId], `/vacancies/${vacancyId}/cover-letters`)
  const gen = useAction(() => post(`/vacancies/${vacancyId}/cover-letters`, { language: lang, tailored_resume_id: tailoredId, use_ai: true }), { invalidate: [['letters', vacancyId]], success: 'Draft created' })
  const exp = useAction(({ id, format }: { id: number; format: 'pdf' | 'docx' }) => post<{ id: number }>(`/cover-letters/${id}/export`, { format }), { onSuccess: (r) => { window.location.href = `/api/exports/${r.id}` } })
  const latest = list.data?.[0]
  return (
    <div className="stack">
      <Button variant="ai" icon={<Sparkles size={16} />} loading={gen.isPending} onClick={() => gen.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Draft cover letter ({lang.toUpperCase()})</Button>
      {latest ? (
        <Card className="stack">
          <pre className="raw" style={{ background: 'transparent', padding: 0, fontFamily: 'inherit', fontSize: 'var(--text-md)' }}>{latest.body}</pre>
          {latest.claims.some((c) => c.issues.length) && <Alert tone="warning" title="Check these sentences">{latest.claims.filter((c) => c.issues.length).map((c) => `“${c.sentence}” — ${c.issues.join(' ')}`).join(' ')}</Alert>}
          <div className="row">
            <Button size="sm" icon={<Download size={14} />} onClick={() => exp.mutate({ id: latest.id, format: 'pdf' })}>PDF</Button>
            <Button size="sm" icon={<Download size={14} />} onClick={() => exp.mutate({ id: latest.id, format: 'docx' })}>DOCX</Button>
          </div>
        </Card>
      ) : <p className="secondary small">No cover letter yet.</p>}
    </div>
  )
}
