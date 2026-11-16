import { useState } from 'react'
import { useParams } from 'react-router'
import { SchemaForm } from '@/components/domain/SchemaForm'
import { HealthBadge } from '@/components/domain/StatusBadge'
import { Alert, Badge, Button, Card, CardTitle, ErrorState, LoadingCards, PageHeader, Select, TextArea, TextInput } from '@/components/ui'
import { del, patch, post, put } from '@/lib/api'
import { fmtDate, fmtRelative, humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'
import type { ConnectorInfo, Paged, RunSummary, Source } from '@/lib/types'

export default function SourceDetailPage() {
  const { id } = useParams()
  const s = useGet<Source>(['source', id], `/sources/${id}`, { refetchInterval: 10000 })
  const runs = useGet<Paged<RunSummary>>(['source-runs', id], `/sources/${id}/runs?limit=20`, { refetchInterval: 10000 })
  const reviews = useGet<{ decision: string; terms_notes: string | null; robots_summary: string | null; reviewer_note: string | null; reviewed_at: string; allowed_paths: string[] }[]>(['source-reviews', id], `/sources/${id}/policy-reviews`)
  const health = useGet<{ health: string; reason: string | null; at: string }[]>(['source-health', id], `/sources/${id}/health-events`)
  const connectors = useGet<ConnectorInfo[]>(['connectors'], '/sources/connectors')
  const [failedRun, setFailedRun] = useState<number | null>(null)
  if (s.isLoading) return <LoadingCards />
  if (s.error || !s.data) return <ErrorState error={s.error} />
  const src = s.data
  const info = connectors.data?.find((c) => c.type === src.connector_type)
  return (
    <>
      <PageHeader crumbs={[{ label: 'Sources', to: '/sources' }, { label: src.name }]} title={src.name} description={`${humanize(src.connector_type)}${src.domain ? ` · ${src.domain}` : ''}`}
        eyebrow={<div className="row" style={{ gap: 6 }}><Badge>{humanize(src.state)}</Badge><Badge>Policy: {humanize(src.policy_status)}</Badge><HealthBadge value={src.health} /></div>} />
      <div className="two-col">
        <div className="stack">
          {info?.auth_required && <SecretCard src={src} />}
          <PolicyReview src={src} />
          {info && <ConfigEditor src={src} info={info} />}
          <Card>
            <CardTitle title="Run history" />
            {!runs.data?.items.length ? <p className="small secondary">No runs yet.</p> : (
              <div className="table-wrap" style={{ boxShadow: 'none' }}>
                <table className="table">
                  <thead><tr><th>Run</th><th>Status</th><th>Items</th><th>When</th><th></th></tr></thead>
                  <tbody>
                    {runs.data.items.map((r) => (
                      <tr key={r.id}>
                        <td className="num">#{r.id} <span className="xs muted">{humanize(r.trigger)}</span></td>
                        <td><Badge tone={r.status === 'SUCCEEDED' ? 'success' : r.status === 'FAILED' ? 'danger' : r.status === 'PARTIAL' || r.status === 'RETRY_SCHEDULED' ? 'warning' : 'neutral'}>{humanize(r.status)}</Badge>{r.error_message && <div className="xs muted">{r.error_message}</div>}</td>
                        <td className="num xs">{r.discovered} seen · {r.new} new · {r.changed} changed · {r.errors} errors</td>
                        <td className="xs">{r.started_at ? fmtRelative(r.started_at) : 'queued'}{r.duration_seconds != null && ` · ${r.duration_seconds.toFixed(1)}s`}</td>
                        <td>{r.errors > 0 && <Button size="sm" variant="ghost" onClick={() => setFailedRun(r.id)}>Failed items</Button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          {failedRun && <FailedItems sourceId={src.id} runId={failedRun} />}
        </div>
        <aside className="stack">
          <Card>
            <CardTitle title="Schedule" as="h2" />
            <dl className="kv">
              <dt>Every</dt><dd>{src.schedule_interval_seconds ? `${Math.round(src.schedule_interval_seconds / 60)} min` : 'Manual only'}</dd>
              <dt>Next check</dt><dd>{src.next_run_at ? fmtRelative(src.next_run_at) : '—'}</dd>
              <dt>Last success</dt><dd>{src.last_success_at ? fmtRelative(src.last_success_at) : 'Never'}</dd>
              <dt>Rate limit</dt><dd>{src.rate_limit_per_minute}/min</dd>
              <dt>Avg duration</dt><dd>{src.stats?.avg_duration_seconds != null ? `${src.stats.avg_duration_seconds.toFixed(1)}s` : '—'}</dd>
            </dl>
          </Card>
          <Card>
            <CardTitle title="Health events" as="h2" />
            <ul className="list-plain stack-sm">{health.data?.map((h, i) => <li key={i} className="small"><HealthBadge value={h.health} /> <span className="muted xs">{fmtRelative(h.at)}</span>{h.reason && <div className="xs muted">{h.reason}</div>}</li>)}</ul>
          </Card>
          <Card>
            <CardTitle title="Policy reviews" as="h2" />
            <ul className="list-plain stack-sm">{reviews.data?.map((r, i) => <li key={i} className="small"><strong>{humanize(r.decision)}</strong> <span className="muted xs">{fmtDate(r.reviewed_at)}</span>{r.terms_notes && <div className="xs">{r.terms_notes}</div>}</li>)}</ul>
          </Card>
        </aside>
      </div>
    </>
  )
}

function PolicyReview({ src }: { src: Source }) {
  const [f, setF] = useState({ decision: 'APPROVED', terms_notes: '', robots_summary: '', reviewer_note: '' })
  const act = useAction(() => post(`/sources/${src.id}/policy-review`, { ...f, allowed_paths: [] }), { invalidate: [['source'], ['source-reviews'], ['sources']], success: 'Review recorded' })
  return (
    <Card className="stack">
      <CardTitle title="Terms & robots review" />
      {src.policy_status === 'UNREVIEWED' && <Alert tone="warning">Read the source's terms and robots.txt before approving. If permission is unclear, choose Denied and use manual import instead.</Alert>}
      <div className="row xs">
        {src.documentation_url && <a href={src.documentation_url} target="_blank" rel="noopener noreferrer">Documentation</a>}
        {src.terms_url && <a href={src.terms_url} target="_blank" rel="noopener noreferrer">Terms</a>}
        {src.domain && <a href={`https://${src.domain}/robots.txt`} target="_blank" rel="noopener noreferrer">robots.txt</a>}
      </div>
      <Select label="Decision" value={f.decision} onChange={(e) => setF({ ...f, decision: e.target.value })} options={[{ value: 'APPROVED', label: 'Approved — collection permitted' }, { value: 'RESTRICTED', label: 'Restricted — permitted with limits' }, { value: 'DENIED', label: 'Denied — do not collect' }]} />
      <TextArea label="What the terms say" value={f.terms_notes} onChange={(e) => setF({ ...f, terms_notes: e.target.value })} />
      <TextInput label="robots.txt summary" value={f.robots_summary} onChange={(e) => setF({ ...f, robots_summary: e.target.value })} />
      <TextInput label="Note" value={f.reviewer_note} onChange={(e) => setF({ ...f, reviewer_note: e.target.value })} />
      <Button variant="primary" loading={act.isPending} disabled={!f.terms_notes} onClick={() => act.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Record review</Button>
    </Card>
  )
}

function ConfigEditor({ src, info }: { src: Source; info: ConnectorInfo }) {
  const [config, setConfig] = useState<Record<string, unknown>>(src.config)
  const [interval, setInterval_] = useState(src.schedule_interval_seconds ? String(src.schedule_interval_seconds / 60) : '')
  const save = useAction(() => patch(`/sources/${src.id}`, { config, schedule_interval_seconds: interval ? Number(interval) * 60 : null }), { invalidate: [['source']], success: 'Configuration saved' })
  if (src.is_system) return null
  return (
    <Card className="stack">
      <CardTitle title="Configuration" />
      <TextInput label="Check every (minutes)" type="number" min={5} value={interval} onChange={(e) => setInterval_(e.target.value)} />
      <SchemaForm schema={info.config_schema} value={config} onChange={setConfig} />
      {save.error && <Alert tone="danger">{errorMessage(save.error)}</Alert>}
      <Button loading={save.isPending} onClick={() => save.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Save configuration</Button>
    </Card>
  )
}

function FailedItems({ sourceId, runId }: { sourceId: number; runId: number }) {
  const q = useGet<{ id: number; url: string | null; external_id: string | null; error: string | null }[]>(['failed', runId], `/sources/${sourceId}/runs/${runId}/items?failed_only=true`)
  return (
    <Card>
      <CardTitle title={`Failed items in run #${runId}`} />
      <ul className="list-plain stack-sm">{q.data?.map((i) => <li key={i.id} className="small wrap-anywhere">{i.url ?? i.external_id} <div className="xs" style={{ color: 'var(--danger)' }}>{i.error}</div></li>)}</ul>
    </Card>
  )
}

function SecretCard({ src }: { src: Source }) {
  const [value, setValue] = useState('')
  const save = useAction(() => put(`/sources/${src.id}/secret`, { value }), { invalidate: [['source']], success: 'Credential saved (encrypted)', onSuccess: () => setValue('') })
  const remove = useAction(() => del(`/sources/${src.id}/secret`), { invalidate: [['source']], success: 'Credential removed' })
  return (
    <Card className="stack">
      <CardTitle title="Credential" />
      <p className="small secondary">
        {src.connector_type === 'email_job_alerts'
          ? 'App password for the alert mailbox (for Gmail: Google Account › Security › 2-Step Verification › App passwords). Stored encrypted; never shown again.'
          : 'Stored encrypted with your master key; never shown again.'}
      </p>
      <Badge tone={src.has_secret ? 'success' : 'warning'}>{src.has_secret ? 'Credential set' : 'No credential yet'}</Badge>
      <TextInput label={src.has_secret ? 'Replace credential' : 'Credential'} type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />
      <div className="row">
        <Button size="sm" variant="primary" disabled={value.length < 4} loading={save.isPending} onClick={() => save.mutate(undefined)}>Save</Button>
        {src.has_secret && <Button size="sm" variant="ghost" onClick={() => remove.mutate(undefined)}>Remove</Button>}
      </div>
    </Card>
  )
}
