import { CheckCircle2, FileUp, Plus, Trash2, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Alert, Badge, Button, Card, CardTitle, Checkbox, EmptyState, ErrorState, LoadingCards, PageHeader, Select, Tabs, TextArea, TextInput } from '@/components/ui'
import { api, post, put } from '@/lib/api'
import { fmtDate, fmtRelative, humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'
import type { Preferences, ProfileData, ProfileVersion } from '@/lib/types'

type Tab = 'profile' | 'preferences' | 'history'
interface Overview {
  active: ProfileVersion | null
  latest_draft: ProfileVersion | null
  versions: Omit<ProfileVersion, 'data'>[]
  resumes: { id: number; filename: string; uploaded_at: string; byte_size: number }[]
}

export default function ProfilePage() {
  const [sp, setSp] = useSearchParams()
  const tab = (sp.get('tab') as Tab) ?? 'profile'
  const ov = useGet<Overview>(['profile'], '/profile', { refetchInterval: false })
  return (
    <>
      <PageHeader title="My Career Profile" description="One master profile, built from your CV and confirmed by you. Tailored CVs never overwrite it." />
      <Tabs<Tab> label="Profile sections" idPrefix="pf" value={tab} onChange={(t) => setSp({ tab: t })} items={[{ value: 'profile', label: 'Profile' }, { value: 'preferences', label: 'Preferences' }, { value: 'history', label: 'Versions & CVs' }]} />
      <div id="pf-panel" role="tabpanel" style={{ marginTop: 'var(--space-4)' }}>
        {ov.isLoading ? <LoadingCards /> : ov.error ? <ErrorState error={ov.error} onRetry={() => void ov.refetch()} /> : ov.data && (
          <>
            {tab === 'profile' && <ProfileTab ov={ov.data} refetch={() => void ov.refetch()} />}
            {tab === 'preferences' && <PreferencesTab />}
            {tab === 'history' && <HistoryTab ov={ov.data} />}
          </>
        )}
      </div>
    </>
  )
}

function Upload({ onUploaded }: { onUploaded: (id: number) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  return (
    <Card tone="soft" className="stack-sm">
      <div className="row-between">
        <div className="stack-sm" style={{ gap: 2 }}>
          <strong>Upload your latest CV</strong>
          <span className="small secondary">PDF or DOCX, up to 10 MB. Stored privately on your server.</span>
        </div>
        <Button variant="primary" icon={<FileUp size={16} />} loading={busy} onClick={() => ref.current?.click()}>Choose file</Button>
      </div>
      <input
        ref={ref}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        hidden
        aria-label="CV file"
        onChange={async (e) => {
          const f = e.target.files?.[0]
          if (!f) return
          setBusy(true)
          setErr(null)
          try {
            const fd = new FormData()
            fd.append('file', f)
            const r = await api<{ resume_id: number }>('/profile/resumes', { method: 'POST', body: fd })
            onUploaded(r.resume_id)
          } catch (x) {
            setErr(errorMessage(x))
          } finally {
            setBusy(false)
            e.target.value = ''
          }
        }}
      />
      {err && <Alert tone="danger">{err}</Alert>}
    </Card>
  )
}

function ProfileTab({ ov, refetch }: { ov: Overview; refetch: () => void }) {
  const [waiting, setWaiting] = useState<number | null>(null)
  const ext = useGet<{ status: string; warnings?: string[]; method?: string }>(['resume-ext', waiting], waiting ? `/profile/resumes/${waiting}/extraction` : null, { refetchInterval: waiting ? 2000 : false })
  useEffect(() => {
    if (ext.data?.status === 'done') {
      setWaiting(null)
      refetch()
    }
  }, [ext.data?.status, refetch])
  const draft = ov.latest_draft
  const startDraft = useAction(() => post<ProfileVersion>('/profile/drafts'), { invalidate: [['profile']] })
  return (
    <div className="stack">
      <Upload onUploaded={setWaiting} />
      {waiting && <Alert tone="info" title="Reading your CV…">Extracting text and structuring sections. This page updates automatically.</Alert>}
      {draft ? (
        <DraftEditor key={draft.id} v={draft} onConfirmed={refetch} />
      ) : ov.active ? (
        <>
          <ProfileView data={ov.active.data} confirmedAt={ov.active.confirmed_at} versionNo={ov.active.version_no} />
          <Button style={{ alignSelf: 'flex-start' }} loading={startDraft.isPending} onClick={() => startDraft.mutate(undefined)}>Edit profile (creates a new draft)</Button>
        </>
      ) : (
        <EmptyState icon={<UserRound size={28} />} title="No profile yet" action={<Button loading={startDraft.isPending} onClick={() => startDraft.mutate(undefined)}>Start manually</Button>}>
          Upload your CV above, or start an empty profile and fill it in yourself.
        </EmptyState>
      )}
    </div>
  )
}

function ProfileView({ data, confirmedAt, versionNo }: { data: ProfileData; confirmedAt: string | null; versionNo: number }) {
  return (
    <Card className="stack">
      <div className="row-between">
        <h2>{data.contact.full_name ?? 'Your profile'}</h2>
        <Badge tone="success" dot>Confirmed v{versionNo}{confirmedAt ? ` · ${fmtDate(confirmedAt)}` : ''}</Badge>
      </div>
      {data.headline && <p>{data.headline}</p>}
      {data.summary && <p className="secondary reading">{data.summary}</p>}
      <Section title="Experience">{data.experiences.map((x) => <Entry key={x.id} title={`${x.title} — ${x.organization}`} meta={`${humanize(x.kind)} · ${x.start ?? '?'} – ${x.end ?? 'present'}`} bullets={x.bullets.map((b) => b.text)} verified={x.verified} />)}</Section>
      <Section title="Projects">{data.projects.map((p) => <Entry key={p.id} title={p.name} meta={p.technologies.join(', ')} bullets={p.bullets.map((b) => b.text)} verified={p.verified} />)}</Section>
      <Section title="Education">{data.educations.map((e) => <Entry key={e.id} title={e.institution} meta={[e.degree, e.field, e.gpa && `GPA ${e.gpa}`].filter(Boolean).join(' · ')} verified={e.verified} />)}</Section>
      <Section title="Skills"><div className="chip-list">{data.skills.map((s) => <Badge key={s.id} tone={s.verified ? 'success' : 'neutral'}>{s.name}</Badge>)}</div></Section>
    </Card>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const arr = Array.isArray(children) ? children : [children]
  if (!arr.length || (Array.isArray(children) && children.length === 0)) return null
  return <section className="stack-sm"><h3>{title}</h3>{children}</section>
}
function Entry({ title, meta, bullets, verified }: { title: string; meta?: string; bullets?: string[]; verified: boolean }) {
  return (
    <div className="stack-sm" style={{ gap: 2 }}>
      <strong className="row" style={{ gap: 6 }}>{title}{verified && <CheckCircle2 size={14} color="var(--success)" aria-label="Verified" />}</strong>
      {meta && <span className="small muted">{meta}</span>}
      {bullets && bullets.length > 0 && <ul className="small" style={{ margin: 0, paddingLeft: '1.2em' }}>{bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}
    </div>
  )
}

const uid = (p: string) => `${p}_${Math.random().toString(16).slice(2, 12)}`

function DraftEditor({ v, onConfirmed }: { v: ProfileVersion; onConfirmed: () => void }) {
  const [d, setD] = useState<ProfileData>(v.data)
  const [dirty, setDirty] = useState(false)
  const upd = (patch: Partial<ProfileData>) => { setD({ ...d, ...patch }); setDirty(true) }
  const save = useAction(() => put<ProfileVersion>(`/profile/versions/${v.id}`, d), { invalidate: [['profile']], success: 'Draft saved', onSuccess: () => setDirty(false) })
  const confirm = useAction(async () => { if (dirty) await put(`/profile/versions/${v.id}`, d); return post(`/profile/versions/${v.id}/confirm`) }, { invalidate: [['profile'], ['vacancies']], success: 'Profile confirmed — matches will refresh', onSuccess: onConfirmed })
  const unverified = [...d.experiences, ...d.educations, ...d.projects, ...d.skills].filter((x) => !x.verified).length
  return (
    <div className="stack">
      <Alert tone="warning" title={`Draft v${v.version_no} — review before confirming`}>
        {v.note} Check every entry against your CV. Tick “verified” for facts you have checked. Nothing here is used for matching or tailoring until you confirm.
        {d.warnings.length > 0 && <ul style={{ margin: '6px 0 0' }}>{d.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      </Alert>
      <Card className="stack">
        <CardTitle title="Basics" />
        <div className="grid grid-2">
          <TextInput label="Full name" value={d.contact.full_name ?? ''} onChange={(e) => upd({ contact: { ...d.contact, full_name: e.target.value || null } })} />
          <TextInput label="Location" value={d.contact.location ?? ''} onChange={(e) => upd({ contact: { ...d.contact, location: e.target.value || null } })} />
          <TextInput label="Email" type="email" value={d.contact.email ?? ''} onChange={(e) => upd({ contact: { ...d.contact, email: e.target.value || null } })} hint="Kept out of AI requests for matching and tailoring." />
          <TextInput label="Phone" value={d.contact.phone ?? ''} onChange={(e) => upd({ contact: { ...d.contact, phone: e.target.value || null } })} />
        </div>
        <TextInput label="Headline" value={d.headline ?? ''} onChange={(e) => upd({ headline: e.target.value || null })} />
        <TextArea label="Summary" value={d.summary ?? ''} onChange={(e) => upd({ summary: e.target.value || null })} />
        <TextArea label="Links (one per line)" value={d.links.join('\n')} onChange={(e) => upd({ links: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean) })} />
      </Card>

      <Card className="stack">
        <div className="card-title"><h3>Experience & organisations</h3><Button size="sm" icon={<Plus size={14} />} onClick={() => upd({ experiences: [...d.experiences, { id: uid('exp'), organization: '', title: '', kind: 'work', location: null, start: null, end: null, bullets: [], verified: true, evidence: null, source: 'user' }] })}>Add</Button></div>
        {d.experiences.map((x, i) => {
          const set = (p: Partial<typeof x>) => upd({ experiences: d.experiences.map((y, j) => (j === i ? { ...y, ...p } : y)) })
          return (
            <fieldset key={x.id} className="card card-soft stack-sm" style={{ border: 0 }}>
              <legend className="sr-only">Experience {i + 1}</legend>
              <div className="grid grid-2">
                <TextInput label="Title" value={x.title} onChange={(e) => set({ title: e.target.value })} />
                <TextInput label="Organisation" value={x.organization} onChange={(e) => set({ organization: e.target.value })} />
                <Select label="Type" value={x.kind} onChange={(e) => set({ kind: e.target.value })} options={['work', 'internship', 'organization', 'volunteer', 'freelance'].map((k) => ({ value: k, label: humanize(k) }))} />
                <TextInput label="Location" value={x.location ?? ''} onChange={(e) => set({ location: e.target.value || null })} />
                <TextInput label="Start" value={x.start ?? ''} onChange={(e) => set({ start: e.target.value || null })} placeholder="e.g. Jan 2025" />
                <TextInput label="End" value={x.end ?? ''} onChange={(e) => set({ end: e.target.value || null })} placeholder="present" />
              </div>
              <span className="label small" style={{ fontWeight: 600 }}>Bullets</span>
              {x.bullets.map((b, bi) => (
                <div key={b.id} className="row" style={{ flexWrap: 'nowrap' }}>
                  <label className="sr-only" htmlFor={b.id}>Bullet {bi + 1}</label>
                  <input id={b.id} className="input" value={b.text} onChange={(e) => set({ bullets: x.bullets.map((y, j) => (j === bi ? { ...y, text: e.target.value } : y)) })} />
                  <Button size="sm" variant="ghost" iconOnly icon={<Trash2 size={14} />} aria-label="Remove bullet" onClick={() => set({ bullets: x.bullets.filter((_, j) => j !== bi) })} />
                </div>
              ))}
              <Button size="sm" variant="ghost" icon={<Plus size={14} />} style={{ alignSelf: 'flex-start' }} onClick={() => set({ bullets: [...x.bullets, { id: uid('b'), text: '', verified: true }] })}>Add bullet</Button>
              {x.evidence && <blockquote className="evidence" style={{ margin: 0 }}>From CV: {x.evidence}</blockquote>}
              <div className="row-between">
                <Checkbox label="Verified by me" checked={x.verified} onChange={(e) => set({ verified: e.target.checked })} />
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={() => upd({ experiences: d.experiences.filter((_, j) => j !== i) })}>Remove</Button>
              </div>
            </fieldset>
          )
        })}
      </Card>

      <Card className="stack">
        <div className="card-title"><h3>Education</h3><Button size="sm" icon={<Plus size={14} />} onClick={() => upd({ educations: [...d.educations, { id: uid('edu'), institution: '', degree: null, field: null, start: null, end: null, gpa: null, current_semester: null, details: [], verified: true, evidence: null, source: 'user' }] })}>Add</Button></div>
        {d.educations.map((x, i) => {
          const set = (p: Partial<typeof x>) => upd({ educations: d.educations.map((y, j) => (j === i ? { ...y, ...p } : y)) })
          return (
            <fieldset key={x.id} className="card card-soft stack-sm" style={{ border: 0 }}>
              <legend className="sr-only">Education {i + 1}</legend>
              <div className="grid grid-2">
                <TextInput label="Institution" value={x.institution} onChange={(e) => set({ institution: e.target.value })} />
                <TextInput label="Degree" value={x.degree ?? ''} onChange={(e) => set({ degree: e.target.value || null })} placeholder="S1 / Bachelor" />
                <TextInput label="Field" value={x.field ?? ''} onChange={(e) => set({ field: e.target.value || null })} />
                <TextInput label="GPA" value={x.gpa ?? ''} onChange={(e) => set({ gpa: e.target.value || null })} />
                <TextInput label="Start" value={x.start ?? ''} onChange={(e) => set({ start: e.target.value || null })} />
                <TextInput label="End" value={x.end ?? ''} onChange={(e) => set({ end: e.target.value || null })} />
              </div>
              {x.evidence && <blockquote className="evidence" style={{ margin: 0 }}>From CV: {x.evidence}</blockquote>}
              <div className="row-between">
                <Checkbox label="Verified by me" checked={x.verified} onChange={(e) => set({ verified: e.target.checked })} />
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={() => upd({ educations: d.educations.filter((_, j) => j !== i) })}>Remove</Button>
              </div>
            </fieldset>
          )
        })}
      </Card>

      <Card className="stack">
        <div className="card-title"><h3>Projects</h3><Button size="sm" icon={<Plus size={14} />} onClick={() => upd({ projects: [...d.projects, { id: uid('prj'), name: '', role: null, start: null, end: null, description: null, bullets: [], technologies: [], url: null, verified: true, evidence: null, source: 'user' }] })}>Add</Button></div>
        {d.projects.map((x, i) => {
          const set = (p: Partial<typeof x>) => upd({ projects: d.projects.map((y, j) => (j === i ? { ...y, ...p } : y)) })
          return (
            <fieldset key={x.id} className="card card-soft stack-sm" style={{ border: 0 }}>
              <legend className="sr-only">Project {i + 1}</legend>
              <TextInput label="Name" value={x.name} onChange={(e) => set({ name: e.target.value })} />
              <TextArea label="Description" value={x.description ?? ''} onChange={(e) => set({ description: e.target.value || null })} />
              <TextInput label="Technologies (comma separated)" value={x.technologies.join(', ')} onChange={(e) => set({ technologies: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) })} />
              <TextInput label="Link" value={x.url ?? ''} onChange={(e) => set({ url: e.target.value || null })} />
              <div className="row-between">
                <Checkbox label="Verified by me" checked={x.verified} onChange={(e) => set({ verified: e.target.checked })} />
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={() => upd({ projects: d.projects.filter((_, j) => j !== i) })}>Remove</Button>
              </div>
            </fieldset>
          )
        })}
      </Card>

      <Card className="stack">
        <CardTitle title="Skills" />
        <div className="chip-list">
          {d.skills.map((s, i) => (
            <span key={s.id} className={`badge ${s.verified ? 'badge-success' : ''}`}>
              <button className="btn-ghost" style={{ border: 0, background: 'none', cursor: 'pointer', padding: 0, color: 'inherit' }} aria-pressed={s.verified} aria-label={`${s.name}: ${s.verified ? 'verified' : 'not verified'} — toggle`} onClick={() => upd({ skills: d.skills.map((y, j) => (j === i ? { ...y, verified: !y.verified } : y)) })}>{s.verified ? '✓ ' : ''}{s.name}</button>
              <button aria-label={`Remove ${s.name}`} style={{ border: 0, background: 'none', cursor: 'pointer', color: 'inherit' }} onClick={() => upd({ skills: d.skills.filter((_, j) => j !== i) })}>×</button>
            </span>
          ))}
        </div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); const f = e.currentTarget.elements.namedItem('newskill') as HTMLInputElement; if (f.value.trim()) { upd({ skills: [...d.skills, { id: uid('sk'), name: f.value.trim(), level: null, verified: true, evidence: null, source: 'user' }] }); f.value = '' } }}>
          <label className="sr-only" htmlFor="newskill">New skill</label>
          <input id="newskill" name="newskill" className="input" style={{ maxWidth: 260 }} placeholder="Add a skill you can evidence" />
          <Button type="submit" size="sm">Add</Button>
        </form>
        <span className="xs muted">Click a skill to toggle “verified”. Only add skills you can back up.</span>
      </Card>

      <Card className="stack">
        <CardTitle title="Languages" />
        <TextArea label="One per line, e.g. “English — professional”" value={d.languages.map((l) => `${l.language}${l.proficiency ? ` — ${l.proficiency}` : ''}`).join('\n')}
          onChange={(e) => upd({ languages: e.target.value.split('\n').filter((x) => x.trim()).map((line, i) => { const [lang, prof] = line.split(/\s+[—-]\s+/); return { id: d.languages[i]?.id ?? uid('lang'), language: (lang ?? '').trim(), proficiency: prof?.trim() || null, verified: true, evidence: null, source: 'user' } }) })} />
      </Card>

      <div className="row" style={{ position: 'sticky', bottom: 'calc(var(--bottomnav-height) + var(--space-5) + var(--safe-bottom))', background: 'var(--surface)', padding: 'var(--space-3)', borderRadius: 'var(--radius-card)', boxShadow: 'var(--shadow-float)' }}>
        <Button loading={save.isPending} disabled={!dirty} onClick={() => save.mutate(undefined)}>Save draft</Button>
        <Button variant="primary" loading={confirm.isPending} onClick={() => confirm.mutate(undefined)}>Confirm as master profile</Button>
        {unverified > 0 && <span className="xs muted">{unverified} entries not yet marked verified</span>}
      </div>
    </div>
  )
}

const ET = ['INTERNSHIP', 'FULL_TIME', 'PART_TIME', 'CONTRACT', 'FREELANCE', 'TRAINEE', 'TEMPORARY', 'VOLUNTEER']
const WA = ['REMOTE', 'HYBRID', 'ONSITE', 'FLEXIBLE']

function PreferencesTab() {
  const q = useGet<Preferences>(['prefs'], '/profile/preferences')
  const [p, setP] = useState<Preferences | null>(null)
  const cur = p ?? q.data ?? null
  const save = useAction(() => put('/profile/preferences', cur), { invalidate: [['prefs'], ['vacancies']], success: 'Preferences saved — matches will refresh' })
  if (q.isLoading || !cur) return <LoadingCards />
  const set = (patch: Partial<Preferences>) => setP({ ...cur, ...patch })
  const list = (k: keyof Preferences, label: string, hint?: string) => (
    <TextInput label={label} hint={hint ?? 'Comma separated'} value={(cur[k] as string[]).join(', ')} onChange={(e) => set({ [k]: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) } as Partial<Preferences>)} />
  )
  const toggles = (k: 'employment_types' | 'work_arrangements', opts: string[], label: string) => (
    <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="small" style={{ fontWeight: 600, marginBottom: 6 }}>{label}</legend>
      <div className="chip-list">
        {opts.map((o) => {
          const on = cur[k].includes(o)
          return <button key={o} type="button" aria-pressed={on} className={`badge ${on ? 'badge-brand' : 'badge-outline'}`} style={{ cursor: 'pointer', minHeight: 32 }} onClick={() => set({ [k]: on ? cur[k].filter((x) => x !== o) : [...cur[k], o] } as Partial<Preferences>)}>{humanize(o)}</button>
        })}
      </div>
    </fieldset>
  )
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(undefined) }}>
      <Card className="stack">
        <CardTitle title="What you are looking for" />
        {list('target_roles', 'Target roles', 'e.g. data analyst, business intelligence, product analyst')}
        {list('industries', 'Preferred industries')}
        {list('skills_to_develop', 'Skills you want to develop')}
        {toggles('employment_types', ET, 'Employment types')}
        {toggles('work_arrangements', WA, 'Work arrangements')}
      </Card>
      <Card className="stack">
        <CardTitle title="Location & pay" />
        {list('preferred_cities', 'Preferred cities', 'e.g. Jakarta, Bandung, Yogyakarta')}
        <Checkbox label="I accept remote work" checked={cur.remote_ok} onChange={(e) => set({ remote_ok: e.target.checked })} />
        <TextInput label="Commute / area note" value={cur.commute_area_note ?? ''} onChange={(e) => set({ commute_area_note: e.target.value || null })} hint="A general area is enough; no precise location is needed." />
        <div className="grid grid-3">
          <TextInput label="Minimum pay" type="number" inputMode="numeric" value={cur.min_compensation ?? ''} onChange={(e) => set({ min_compensation: e.target.value ? Number(e.target.value) : null })} />
          <Select label="Currency" value={cur.compensation_currency} onChange={(e) => set({ compensation_currency: e.target.value })} options={['IDR', 'USD', 'SGD', 'EUR', 'MYR'].map((c) => ({ value: c, label: c }))} />
          <Select label="Per" value={cur.compensation_period} onChange={(e) => set({ compensation_period: e.target.value })} options={[{ value: 'MONTH', label: 'Month' }, { value: 'YEAR', label: 'Year' }, { value: 'HOUR', label: 'Hour' }]} />
        </div>
      </Card>
      <Card className="stack">
        <CardTitle title="Eligibility & exclusions" />
        <div className="grid grid-2">
          <Select label="Education level" value={cur.education_level ?? ''} onChange={(e) => set({ education_level: e.target.value || null })} options={[{ value: '', label: 'Not set' }, ...['STUDENT', 'HIGH_SCHOOL', 'DIPLOMA', 'BACHELOR', 'MASTER', 'DOCTORATE'].map((x) => ({ value: x, label: humanize(x) }))]} />
          <TextInput label="Current semester" type="number" min={1} max={16} value={cur.current_semester ?? ''} onChange={(e) => set({ current_semester: e.target.value ? Number(e.target.value) : null })} />
        </div>
        {list('excluded_companies', 'Excluded companies')}
        {list('excluded_industries', 'Excluded industries')}
        {list('excluded_keywords', 'Excluded keywords')}
        <TextArea label="Career goals" value={cur.career_goals ?? ''} onChange={(e) => set({ career_goals: e.target.value || null })} />
        <Select label="Default document language" value={cur.language} onChange={(e) => set({ language: e.target.value as 'id' | 'en' })} options={[{ value: 'id', label: 'Bahasa Indonesia' }, { value: 'en', label: 'English' }]} />
      </Card>
      <Button type="submit" variant="primary" loading={save.isPending} style={{ alignSelf: 'flex-start' }}>Save preferences</Button>
    </form>
  )
}

function HistoryTab({ ov }: { ov: Overview }) {
  return (
    <div className="grid grid-2">
      <Card>
        <CardTitle title="Profile versions" />
        <ul className="list-plain stack-sm">
          {ov.versions.map((v) => (
            <li key={v.id} className="row-between small">
              <span>v{v.version_no} · {v.note}</span>
              <Badge tone={v.status === 'CONFIRMED' ? 'success' : v.status === 'DRAFT' ? 'warning' : 'outline'}>{humanize(v.status)}</Badge>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardTitle title="Uploaded CVs" />
        <ul className="list-plain stack-sm">
          {ov.resumes.map((r) => (
            <li key={r.id} className="row-between small">
              <a href={`/api/profile/resumes/${r.id}/file`}>{r.filename}</a>
              <span className="muted">{fmtRelative(r.uploaded_at)}</span>
            </li>
          ))}
        </ul>
        <p className="xs muted" style={{ marginTop: 'var(--space-3)' }}>Originals are kept unchanged. Downloads require your session.</p>
      </Card>
    </div>
  )
}
