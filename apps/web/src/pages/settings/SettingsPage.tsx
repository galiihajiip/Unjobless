import { DatabaseBackup, Download, KeyRound, LogOut, Smartphone } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Alert, Badge, Button, Card, CardTitle, Checkbox, LoadingCards, PageHeader, Select, TextInput } from '@/components/ui'
import { del, post, put } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { fmtDate, fmtRelative, humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'

interface AppPrefs { theme: string; language: string; raw_retention_days: number | null; notify_in_app: boolean; notify_deadline_days: number; backup_keep: number }
interface SettingsOut { app: AppPrefs; limits: Record<string, number>; environment: { env: string; master_key_configured: boolean; user_agent: string } }

export default function SettingsPage() {
  const s = useGet<SettingsOut>(['settings'], '/settings')
  const [p, setP] = useState<AppPrefs | null>(null)
  const cur = p ?? s.data?.app ?? null
  const save = useAction(() => put('/settings', cur), { invalidate: [['settings']], success: 'Settings saved' })
  if (s.isLoading || !cur || !s.data) return <LoadingCards />
  return (
    <>
      <PageHeader title="Settings" description="Preferences, security, backups and data export for your private instance." />
      <div className="grid grid-2">
        <Card className="stack">
          <CardTitle title="General" />
          <Select label="Interface language" value={cur.language} onChange={(e) => setP({ ...cur, language: e.target.value })} options={[{ value: 'en', label: 'English' }, { value: 'id', label: 'Bahasa Indonesia (documents)' }]} hint="Document language for CVs/letters is chosen per document." />
          <Select label="Theme" value={cur.theme} onChange={(e) => setP({ ...cur, theme: e.target.value })} options={[{ value: 'light', label: 'Light' }]} hint="Dark mode is not available yet." />
          <Checkbox label="In-app reminders for deadlines and follow-ups" checked={cur.notify_in_app} onChange={(e) => setP({ ...cur, notify_in_app: e.target.checked })} />
          <TextInput label="Remind me this many days before a deadline" type="number" min={1} max={30} value={cur.notify_deadline_days} onChange={(e) => setP({ ...cur, notify_deadline_days: Number(e.target.value) })} />
          <TextInput label="Delete uncited raw source copies after (days)" type="number" min={30} placeholder="Keep forever" value={cur.raw_retention_days ?? ''} onChange={(e) => setP({ ...cur, raw_retention_days: e.target.value ? Number(e.target.value) : null })} hint="Raw copies that are evidence for a saved vacancy are always kept." />
          <TextInput label="Backups to keep" type="number" min={1} max={90} value={cur.backup_keep} onChange={(e) => setP({ ...cur, backup_keep: Number(e.target.value) })} />
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Save</Button>
        </Card>
        <Security />
        <Backups masterKey={s.data.environment.master_key_configured} />
        <Card className="stack">
          <CardTitle title="Export your data" />
          <p className="small secondary">JSON inside a ZIP. No passwords, sessions or API keys are included.</p>
          <div className="row">
            {['all', 'profile', 'vacancies', 'applications', 'sources'].map((k) => <a key={k} className="btn btn-secondary btn-sm" href={`/api/settings/export?kind=${k}`}><Download size={14} /> {humanize(k)}</a>)}
          </div>
        </Card>
        <Card className="stack">
          <CardTitle title="Install the app" />
          <p className="small secondary">Add Unjobless to your home screen or dock for an app-like window.</p>
          <Link className="btn btn-secondary btn-sm" to="/settings/install" style={{ alignSelf: 'flex-start' }}><Smartphone size={14} /> Installation help</Link>
        </Card>
        <Card className="stack">
          <CardTitle title="Limits (server configuration)" />
          <dl className="kv">{Object.entries(s.data.limits).map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{humanize(k)}</dt><dd className="num">{v.toLocaleString()}</dd></div>)}</dl>
          <span className="xs muted">Crawler user agent: {s.data.environment.user_agent}</span>
        </Card>
      </div>
      <AuditLog />
    </>
  )
}

function Security() {
  const { logout } = useAuth()
  const sessions = useGet<{ id: number; created_at: string; last_seen_at: string; user_agent: string | null; current: boolean }[]>(['sessions'], '/auth/sessions')
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const change = useAction(() => post('/auth/password', pw), { success: 'Password changed — other sessions were signed out', invalidate: [['sessions']], onSuccess: () => setPw({ current_password: '', new_password: '' }) })
  const revoke = useAction((id: number) => del(`/auth/sessions/${id}`), { invalidate: [['sessions']] })
  const all = useAction(() => post('/auth/logout-all'), { onSuccess: () => void logout() })
  return (
    <Card className="stack">
      <CardTitle title="Security" />
      <ul className="list-plain stack-sm">
        {sessions.data?.map((x) => (
          <li key={x.id} className="row-between small">
            <span className="truncate" style={{ maxWidth: 260 }}>{x.current && <Badge tone="brand">This device</Badge>} {x.user_agent ?? 'Unknown device'}<div className="xs muted">active {fmtRelative(x.last_seen_at)} · since {fmtDate(x.created_at)}</div></span>
            {!x.current && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(x.id)}>Revoke</Button>}
          </li>
        ))}
      </ul>
      <Button size="sm" variant="ghost" icon={<LogOut size={14} />} onClick={() => all.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Sign out everywhere</Button>
      <form className="stack-sm" onSubmit={(e) => { e.preventDefault(); change.mutate(undefined) }}>
        <TextInput label="Current password" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
        <TextInput label="New password" type="password" autoComplete="new-password" minLength={12} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} hint="At least 12 characters." />
        <Button type="submit" size="sm" icon={<KeyRound size={14} />} disabled={pw.new_password.length < 12 || !pw.current_password} loading={change.isPending} style={{ alignSelf: 'flex-start' }}>Change password</Button>
      </form>
    </Card>
  )
}

function Backups({ masterKey }: { masterKey: boolean }) {
  const list = useGet<{ name: string; created_at: string; bytes: number; alembic_revision: string; row_counts: Record<string, number> }[]>(['backups'], '/settings/backups')
  const make = useAction(() => post('/settings/backups'), { invalidate: [['backups']], success: 'Backup created' })
  return (
    <Card className="stack">
      <CardTitle title="Backups" />
      <p className="small secondary">Database + private files + checksummed manifest, saved on the server's backup volume. Copy them off the server regularly. Scheduled backups are configured in the deployment guide.</p>
      {!masterKey && <Alert tone="warning">No master key is configured; AI keys cannot be stored.</Alert>}
      <Alert tone="info">Keep UNJOBLESS_MASTER_KEY in a password manager. Without it, a restored backup keeps everything except stored AI keys.</Alert>
      <Button size="sm" icon={<DatabaseBackup size={14} />} loading={make.isPending} onClick={() => make.mutate(undefined)} style={{ alignSelf: 'flex-start' }}>Create backup now</Button>
      {make.error && <Alert tone="danger">{errorMessage(make.error)}</Alert>}
      <ul className="list-plain stack-sm">{list.data?.map((b) => <li key={b.name} className="small row-between"><code>{b.name}</code><span className="muted num">{(b.bytes / 1e6).toFixed(1)} MB</span></li>)}</ul>
    </Card>
  )
}

function AuditLog() {
  const q = useGet<{ action: string; actor: string; target: string; at: string }[]>(['audit'], '/settings/audit')
  return (
    <Card style={{ marginTop: 'var(--space-5)' }}>
      <CardTitle title="Audit log" />
      <ul className="list-plain stack-sm">{q.data?.slice(0, 40).map((a, i) => <li key={i} className="small row-between"><span>{a.action} <span className="muted xs">{a.target}</span></span><span className="xs muted">{humanize(a.actor)} · {fmtRelative(a.at)}</span></li>)}</ul>
    </Card>
  )
}
