import { DatabaseZap, Pause, Play, Plus, ShieldBan, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { SchemaForm } from '@/components/domain/SchemaForm'
import { HealthBadge } from '@/components/domain/StatusBadge'
import { Alert, Badge, Button, Card, CardTitle, Checkbox, Dialog, EmptyState, ErrorState, LoadingCards, PageHeader, Select, TextArea, TextInput } from '@/components/ui'
import { del, post } from '@/lib/api'
import { fmtRelative, humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'
import type { ConnectorInfo, Source } from '@/lib/types'

export default function SourcesPage() {
  const list = useGet<Source[]>(['sources'], '/sources', { refetchInterval: 15000 })
  const [adding, setAdding] = useState(false)
  const [pack, setPack] = useState(false)
  const inv = [['sources'], ['overview']]
  const run = useAction((id: number) => post(`/sources/${id}/run`), { invalidate: inv, success: 'Run queued' })
  const state = useAction(({ id, action }: { id: number; action: string }) => post(`/sources/${id}/${action}`), { invalidate: inv, success: 'Updated' })
  return (
    <>
      <PageHeader title="Sources" description="Where Unjobless may collect from. New sources start disabled until you review their terms and robots policy." actions={<><Button icon={<Sparkles size={16} />} onClick={() => setPack(true)}>Recommended sources</Button><Button variant="primary" icon={<Plus size={16} />} onClick={() => setAdding(true)}>Add source</Button></>} />
      <Alert tone="info">Collection is never real-time and never “all of the internet”. Each source shows when it was last checked and when it is next due.</Alert>
      <div className="stack" style={{ marginTop: 'var(--space-4)' }}>
        {list.isLoading ? <LoadingCards /> : list.error ? <ErrorState error={list.error} /> : !list.data?.length ? (
          <EmptyState icon={<DatabaseZap size={28} />} title="No sources yet" action={<Button variant="primary" onClick={() => setAdding(true)}>Add a source</Button>}>Add a public ATS job board (Greenhouse, Lever, Ashby) or a company careers page you have reviewed.</EmptyState>
        ) : list.data.map((s) => (
          <Card key={s.id} className="stack-sm">
            <div className="row-between">
              <div className="stack-sm" style={{ gap: 2, minWidth: 0 }}>
                <Link to={`/sources/${s.id}`} style={{ color: 'inherit' }}><h3 className="truncate">{s.name}</h3></Link>
                <span className="xs muted">{humanize(s.connector_type)}{s.domain ? ` · ${s.domain}` : ''}</span>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <Badge tone={s.state === 'ENABLED' ? 'success' : s.state === 'PAUSED' ? 'warning' : 'outline'}>{humanize(s.state)}</Badge>
                <Badge tone={s.policy_status === 'APPROVED' ? 'success' : s.policy_status === 'DENIED' ? 'danger' : 'warning'}>Policy: {humanize(s.policy_status)}</Badge>
                <HealthBadge value={s.health} title={s.health_reason ?? undefined} />
              </div>
            </div>
            <span className="xs muted">
              Last success {s.last_success_at ? fmtRelative(s.last_success_at) : 'never'} · last checked {s.last_attempt_at ? fmtRelative(s.last_attempt_at) : 'never'} · next check {s.next_run_at ? fmtRelative(s.next_run_at) : '—'}
              {s.stats && ` · ${s.stats.discovered} items seen in ${s.stats.runs} runs`}
            </span>
            {s.health_reason && s.health !== 'HEALTHY' && <Alert tone="warning">{s.health_reason}</Alert>}
            {s.active_run && <Alert tone="info">Run #{s.active_run.id} {humanize(s.active_run.status)}{s.active_run.retry_at ? ` — retry ${fmtRelative(s.active_run.retry_at)}` : ''}</Alert>}
            <div className="row">
              {s.state === 'ENABLED' && <Button size="sm" variant="secondary" icon={<Play size={14} />} loading={run.isPending} onClick={() => run.mutate(s.id)} disabled={!!s.active_run}>Run now</Button>}
              {s.state === 'ENABLED' && <Button size="sm" variant="ghost" icon={<Pause size={14} />} onClick={() => state.mutate({ id: s.id, action: 'pause' })}>Pause</Button>}
              {s.state === 'PAUSED' && <Button size="sm" variant="secondary" icon={<Play size={14} />} onClick={() => state.mutate({ id: s.id, action: 'resume' })}>Resume</Button>}
              {s.state === 'DISABLED' && (s.policy_status === 'APPROVED' || s.policy_status === 'RESTRICTED') && <Button size="sm" variant="secondary" onClick={() => state.mutate({ id: s.id, action: 'enable' })}>Enable</Button>}
              {s.policy_status === 'UNREVIEWED' && <Link className="btn btn-sm btn-primary" to={`/sources/${s.id}`}>Review policy</Link>}
              <Link className="btn btn-sm btn-ghost" to={`/sources/${s.id}`}>Details</Link>
            </div>
          </Card>
        ))}
      </div>
      <Exclusions />
      {adding && <AddSource onClose={() => setAdding(false)} />}
      {pack && <StarterPack onClose={() => setPack(false)} existing={(list.data ?? []).map((s) => s.key)} />}
    </>
  )
}

function AddSource({ onClose }: { onClose: () => void }) {
  const connectors = useGet<ConnectorInfo[]>(['connectors'], '/sources/connectors')
  const [type, setType] = useState('')
  const [form, setForm] = useState({ key: '', name: '', domain: '', interval: '' })
  const [config, setConfig] = useState<Record<string, unknown>>({})
  const info = connectors.data?.find((c) => c.type === type)
  const create = useAction(() => post<Source>('/sources', {
    key: form.key, name: form.name, connector_type: type, domain: form.domain || null, config,
    schedule_interval_seconds: form.interval ? Number(form.interval) * 60 : null,
  }), { invalidate: [['sources']], success: 'Source added (disabled until reviewed)', onSuccess: onClose })
  return (
    <Dialog open onClose={onClose} title="Add a source" description="Only add sources you are allowed to collect from." actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!type || !form.key || !form.name} loading={create.isPending} onClick={() => create.mutate(undefined)}>Add</Button></>}>
      <Select label="Connector" value={type} onChange={(e) => { setType(e.target.value); setConfig({}) }} options={[{ value: '', label: 'Choose…' }, ...(connectors.data ?? []).map((c) => ({ value: c.type, label: c.name }))]} />
      {info && (
        <Card tone="soft" className="stack-sm">
          <span className="small">{info.description}</span>
          <span className="xs muted">{info.terms_review}</span>
          <span className="row xs">{info.documentation_url && <a href={info.documentation_url} target="_blank" rel="noopener noreferrer">Documentation</a>}{info.terms_url && <a href={info.terms_url} target="_blank" rel="noopener noreferrer">Terms</a>}</span>
        </Card>
      )}
      <div className="grid grid-2">
        <TextInput label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value, key: form.key || e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') })} />
        <TextInput label="Key" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} hint="Lowercase letters, numbers and dashes." />
        <TextInput label="Domain" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} hint={type === 'career_page' ? 'Required: the crawler never leaves this domain.' : 'Optional'} />
        <TextInput label="Check every (minutes)" type="number" min={5} value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value })} hint={info?.default_schedule_seconds ? `Default ${info.default_schedule_seconds / 60} min. Minimum 5.` : undefined} />
      </div>
      {info && <SchemaForm schema={info.config_schema} value={config} onChange={setConfig} />}
      {create.error && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
    </Dialog>
  )
}

function Exclusions() {
  const list = useGet<{ id: number; pattern: string; reason: string }[]>(['exclusions'], '/sources/exclusions')
  const [pattern, setPattern] = useState('')
  const [reason, setReason] = useState('')
  const add = useAction(() => post('/sources/exclusions', { pattern, reason }), { invalidate: [['exclusions'], ['sources']], success: 'Excluded', onSuccess: () => { setPattern(''); setReason('') } })
  const remove = useAction((id: number) => del(`/sources/exclusions/${id}`), { invalidate: [['exclusions']] })
  return (
    <Card className="stack" style={{ marginTop: 'var(--space-5)' }}>
      <CardTitle title="Exclusion list" />
      <p className="small secondary">Domains or URL prefixes that must never be collected or imported (e.g. sites whose terms forbid it).</p>
      <ul className="list-plain stack-sm">
        {list.data?.map((e) => (
          <li key={e.id} className="row-between small">
            <span><ShieldBan size={14} aria-hidden="true" style={{ display: 'inline' }} /> <code>{e.pattern}</code> <span className="muted">— {e.reason}</span></span>
            <Button size="sm" variant="ghost" iconOnly icon={<Trash2 size={14} />} aria-label={`Remove exclusion ${e.pattern}`} onClick={() => remove.mutate(e.id)} />
          </li>
        ))}
      </ul>
      <div className="grid grid-2">
        <TextInput label="Domain or URL prefix" value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="example.com" />
        <TextArea label="Reason" rows={1} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <Button size="sm" disabled={!pattern || !reason} loading={add.isPending} onClick={() => add.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Add exclusion</Button>
    </Card>
  )
}

interface PackItem { key: string; name: string; connector_name: string; terms_review: string; attribution: string; documentation_url: string | null }

function StarterPack({ onClose, existing }: { onClose: () => void; existing: string[] }) {
  const q = useGet<PackItem[]>(['starter-pack'], '/sources/starter-pack')
  const [sel, setSel] = useState<string[] | null>(null)
  const items = (q.data ?? []).filter((p) => !existing.includes(p.key))
  const chosen = sel ?? items.map((p) => p.key)
  const act = useAction(() => post<Source[]>('/sources/starter-pack', { keys: chosen }), { invalidate: [['sources'], ['overview']], success: (r) => `${r.length} sources added and running`, onSuccess: onClose })
  return (
    <Dialog open onClose={onClose} title="Recommended sources" description="Public, documented job APIs verified to list jobs in Indonesia or remote jobs open to Indonesian applicants. Adding them records your approval of each source's API terms."
      actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!chosen.length} loading={act.isPending} onClick={() => act.mutate(undefined)}>Approve & add {chosen.length}</Button></>}>
      {!items.length ? <p className="small secondary">All recommended sources are already added.</p> : (
        <ul className="list-plain stack-sm">
          {items.map((p) => (
            <li key={p.key} className="stack-sm" style={{ gap: 2 }}>
              <Checkbox label={<span><strong>{p.name}</strong> <span className="muted xs">· {p.connector_name}</span></span>} checked={chosen.includes(p.key)} onChange={(e) => setSel(e.target.checked ? [...chosen, p.key] : chosen.filter((k) => k !== p.key))} />
              <span className="xs muted" style={{ paddingLeft: 26 }}>{p.terms_review}</span>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  )
}
