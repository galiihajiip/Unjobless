import { Bot, KeyRound, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Alert, Badge, Button, Card, CardTitle, Checkbox, Dialog, EmptyState, LoadingCards, PageHeader, Select, TextInput } from '@/components/ui'
import { del, patch, post, put } from '@/lib/api'
import { fmtRelative, humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'
import type { AIProvider } from '@/lib/types'

interface Usage { days: number; by_task: { task: string; calls: number; input_tokens: number; output_tokens: number; cost_estimate_usd: number | null }[]; recent_runs: { id: number; task: string; status: string; model: string | null; attempts: number; error: string | null; created_at: string }[] }
interface Tasks { tasks: { name: string; version: string; effort: string; max_tokens: number; route: { provider_id: number | null; model: string | null } | null }[] }

export default function AIStudioPage() {
  const providers = useGet<AIProvider[]>(['ai-providers'], '/ai/providers')
  const usage = useGet<Usage>(['ai-usage'], '/ai/usage?days=30')
  const tasks = useGet<Tasks>(['ai-tasks'], '/ai/tasks')
  const budget = useGet<{ daily_budget_usd: number | null; spent_last_24h_usd: number }>(['ai-budget'], '/ai/budget')
  const [adding, setAdding] = useState(false)
  const [rotating, setRotating] = useState<AIProvider | null>(null)
  const inv = [['ai-providers']]
  const test = useAction((id: number) => post<{ ok: boolean; message: string }>(`/ai/providers/${id}/test`), { invalidate: inv, success: (r) => r.message })
  const upd = useAction(({ id, body }: { id: number; body: Record<string, unknown> }) => patch(`/ai/providers/${id}`, body), { invalidate: inv, success: 'Saved' })
  const delKey = useAction((id: number) => del(`/ai/providers/${id}/key`), { invalidate: inv, success: 'Key deleted' })
  const remove = useAction((id: number) => del(`/ai/providers/${id}`), { invalidate: inv, success: 'Provider removed' })
  const [budgetVal, setBudgetVal] = useState('')
  const saveBudget = useAction(() => put('/ai/budget', { daily_budget_usd: budgetVal === '' ? null : Number(budgetVal) }), { invalidate: [['ai-budget']], success: 'Budget saved' })
  const [routes, setRoutes] = useState<Record<string, { provider_id: number | null; model: string | null }>>({})
  const saveRoutes = useAction(() => put('/ai/tasks/routes', { routes }), { invalidate: [['ai-tasks']], success: 'Routing saved' })
  return (
    <>
      <PageHeader title="AI Studio" description="Optional. Unjobless works without AI using rule-based extraction; a provider adds richer extraction, classification of ambiguous posts, CV structuring and tailoring." actions={<Button variant="primary" icon={<Plus size={16} />} onClick={() => setAdding(true)}>Add provider</Button>} />
      <Alert tone="info">Keys are encrypted on the server with your master key and are never shown again — only the last four characters. Scraped content is sent as data, never as instructions, and the model cannot take actions. Rate limits are respected: a limited provider cools down instead of being swapped for another key.</Alert>
      <div className="stack" style={{ marginTop: 'var(--space-4)' }}>
        {providers.isLoading ? <LoadingCards /> : !providers.data?.length ? (
          <EmptyState icon={<Bot size={28} />} title="No AI provider" action={<Button variant="primary" onClick={() => setAdding(true)}>Add provider</Button>}>Add an Anthropic (Claude) key or another provider you have an account with.</EmptyState>
        ) : providers.data.map((p) => (
          <Card key={p.id} className="stack-sm">
            <div className="row-between">
              <div className="stack-sm" style={{ gap: 2 }}>
                <h3>{p.name}</h3>
                <span className="xs muted">{humanize(p.kind)} · model {p.default_model ?? '—'}{p.base_url ? ` · ${p.base_url}` : ''}</span>
              </div>
              <div className="row" style={{ gap: 6 }}>
                {p.is_default && <Badge tone="brand">Default</Badge>}
                {p.allow_as_fallback && <Badge>Fallback</Badge>}
                <Badge tone={p.has_key ? 'success' : 'warning'}>{p.has_key ? `Key ${p.key_hint}` : 'No key'}</Badge>
                {!p.enabled && <Badge tone="outline">Disabled</Badge>}
              </div>
            </div>
            {p.cooldown_until && new Date(p.cooldown_until) > new Date() && <Alert tone="warning">Cooling down after a rate limit until {new Date(p.cooldown_until).toLocaleTimeString()}.</Alert>}
            {p.last_error && <Alert tone="danger">{p.last_error}</Alert>}
            <span className="xs muted">{p.last_tested_at ? `Last tested ${fmtRelative(p.last_tested_at)}` : 'Not tested yet'}</span>
            <div className="row">
              <Button size="sm" variant="secondary" loading={test.isPending} onClick={() => test.mutate(p.id)}>Test connection</Button>
              <Button size="sm" icon={<KeyRound size={14} />} onClick={() => setRotating(p)}>{p.has_key ? 'Replace key' : 'Add key'}</Button>
              {!p.is_default && <Button size="sm" variant="ghost" onClick={() => upd.mutate({ id: p.id, body: { is_default: true } })}>Make default</Button>}
              <Button size="sm" variant="ghost" onClick={() => upd.mutate({ id: p.id, body: { enabled: !p.enabled } })}>{p.enabled ? 'Disable' : 'Enable'}</Button>
              <Button size="sm" variant="ghost" onClick={() => upd.mutate({ id: p.id, body: { allow_as_fallback: !p.allow_as_fallback } })}>{p.allow_as_fallback ? 'Not a fallback' : 'Use as outage fallback'}</Button>
              {p.has_key && <Button size="sm" variant="ghost" onClick={() => delKey.mutate(p.id)}>Delete key</Button>}
              <Button size="sm" variant="danger" iconOnly icon={<Trash2 size={14} />} aria-label={`Remove ${p.name}`} onClick={() => remove.mutate(p.id)} />
            </div>
          </Card>
        ))}
      </div>
      <div className="grid grid-2" style={{ marginTop: 'var(--space-5)' }}>
        <Card className="stack">
          <CardTitle title="Daily budget" />
          <span className="small">Spent in the last 24h: <strong className="num">${budget.data?.spent_last_24h_usd.toFixed(4) ?? '0'}</strong> (estimate)</span>
          <TextInput label="Stop AI tasks after (USD / 24h)" type="number" min={0} step="0.5" placeholder={budget.data?.daily_budget_usd != null ? String(budget.data.daily_budget_usd) : 'No limit'} value={budgetVal} onChange={(e) => setBudgetVal(e.target.value)} />
          <Button size="sm" loading={saveBudget.isPending} onClick={() => saveBudget.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Save budget</Button>
        </Card>
        <Card className="stack">
          <CardTitle title="Usage (30 days)" />
          {!usage.data?.by_task.length ? <p className="small secondary">No AI calls yet.</p> : (
            <ul className="list-plain stack-sm">{usage.data.by_task.map((u) => <li key={u.task} className="row-between small"><span>{humanize(u.task)}</span><span className="num muted">{u.calls} calls · {(u.input_tokens + u.output_tokens).toLocaleString()} tokens{u.cost_estimate_usd != null && ` · $${u.cost_estimate_usd.toFixed(3)}`}</span></li>)}</ul>
          )}
        </Card>
      </div>
      <Card className="stack" style={{ marginTop: 'var(--space-5)' }}>
        <CardTitle title="Task routing" />
        <p className="xs muted">Leave blank to use the default provider and its model. Prompt versions are recorded with every result.</p>
        {tasks.data?.tasks.map((t) => (
          <div key={t.name} className="grid grid-3" style={{ alignItems: 'end' }}>
            <span className="small"><strong>{humanize(t.name)}</strong> <span className="muted xs">v{t.version} · effort {t.effort}</span></span>
            <Select label="Provider" value={String((routes[t.name] ?? t.route)?.provider_id ?? '')} onChange={(e) => setRoutes({ ...routes, [t.name]: { model: (routes[t.name] ?? t.route)?.model ?? null, provider_id: e.target.value ? Number(e.target.value) : null } })} options={[{ value: '', label: 'Default' }, ...(providers.data ?? []).map((p) => ({ value: String(p.id), label: p.name }))]} />
            <TextInput label="Model override" value={(routes[t.name] ?? t.route)?.model ?? ''} onChange={(e) => setRoutes({ ...routes, [t.name]: { provider_id: (routes[t.name] ?? t.route)?.provider_id ?? null, model: e.target.value || null } })} />
          </div>
        ))}
        <Button size="sm" disabled={!Object.keys(routes).length} loading={saveRoutes.isPending} onClick={() => saveRoutes.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Save routing</Button>
      </Card>
      {usage.data?.recent_runs.length ? (
        <Card style={{ marginTop: 'var(--space-5)' }}>
          <CardTitle title="Recent AI runs" />
          <ul className="list-plain stack-sm">{usage.data.recent_runs.slice(0, 15).map((r) => <li key={r.id} className="small row-between"><span>{humanize(r.task)} <span className="muted xs">{r.model}</span></span><span><Badge tone={r.status === 'SUCCEEDED' ? 'success' : r.status === 'RATE_LIMITED' ? 'warning' : 'danger'}>{humanize(r.status)}</Badge> <span className="xs muted">{fmtRelative(r.created_at)}</span></span></li>)}</ul>
        </Card>
      ) : null}
      {adding && <AddProvider onClose={() => setAdding(false)} />}
      {rotating && <KeyDialog p={rotating} onClose={() => setRotating(null)} />}
    </>
  )
}

function AddProvider({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ name: 'Claude', kind: 'anthropic', base_url: '', api_key: '', default_model: 'claude-opus-5-5', is_default: true, allow_as_fallback: false })
  const act = useAction(() => post('/ai/providers', { ...f, base_url: f.base_url || null, api_key: f.api_key || null, default_model: f.default_model || null }), { invalidate: [['ai-providers']], success: 'Provider added — run a connection test', onSuccess: onClose })
  return (
    <Dialog open onClose={onClose} title="Add AI provider" actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={act.isPending} onClick={() => act.mutate(undefined)}>Add</Button></>}>
      <Select label="Kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value, default_model: e.target.value === 'anthropic' ? 'claude-opus-5-5' : '' })} options={[{ value: 'anthropic', label: 'Anthropic (Claude)' }, { value: 'openai_compatible', label: 'OpenAI-compatible API (other providers)' }]} />
      <TextInput label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      {f.kind !== 'anthropic' && <TextInput label="Base URL (https)" value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} placeholder="https://api.example.com/v1" />}
      <TextInput label="Model" value={f.default_model} onChange={(e) => setF({ ...f, default_model: e.target.value })} hint={f.kind === 'anthropic' ? 'Default: claude-opus-5-5. Cheaper options: claude-sonnet-5-5, claude-haiku-5-5.' : undefined} />
      <TextInput label="API key" type="password" autoComplete="off" value={f.api_key} onChange={(e) => setF({ ...f, api_key: e.target.value })} hint="Encrypted at rest. It will not be shown again." />
      <Checkbox label="Make default" checked={f.is_default} onChange={(e) => setF({ ...f, is_default: e.target.checked })} />
      <Checkbox label="Allow as fallback during outages (not for rate limits)" checked={f.allow_as_fallback} onChange={(e) => setF({ ...f, allow_as_fallback: e.target.checked })} />
      {act.error && <Alert tone="danger">{errorMessage(act.error)}</Alert>}
    </Dialog>
  )
}

function KeyDialog({ p, onClose }: { p: AIProvider; onClose: () => void }) {
  const [key, setKey] = useState('')
  const act = useAction(() => patch(`/ai/providers/${p.id}`, { api_key: key }), { invalidate: [['ai-providers']], success: 'Key replaced', onSuccess: onClose })
  return (
    <Dialog open onClose={onClose} title={`${p.has_key ? 'Replace' : 'Add'} key for ${p.name}`} actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={key.length < 8} loading={act.isPending} onClick={() => act.mutate(undefined)}>Save key</Button></>}>
      <TextInput label="New API key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
    </Dialog>
  )
}
