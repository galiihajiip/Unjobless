import { Columns2, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingCards, Meter, PageHeader } from '@/components/ui'
import { get, post, put } from '@/lib/api'
import { humanize } from '@/lib/format'
import { errorMessage, useAction, useGet } from '@/lib/queries'
import type { Comparison, Paged, VacancyCard } from '@/lib/types'

const WIN_TONE = { A: 'brand', B: 'info', Tie: 'neutral', Unknown: 'outline' } as const

export default function ComparePage() {
  const [sp, setSp] = useSearchParams()
  const ids = (sp.get('ids') ?? '').split(',').map(Number).filter(Boolean)
  const [weights, setWeights] = useState<Record<string, number> | null>(null)
  const [result, setResult] = useState<Comparison | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const defaults = useGet<{ weights: Record<string, number> }>(['compare-defaults'], '/compare/defaults')
  const history = useGet<{ id: number; created_at: string; lean: string; vacancies: { id: number; title: string; company: string | null }[] }[]>(['compare-history'], '/compare/history')
  const w = weights ?? defaults.data?.weights ?? null

  const run = async (save: boolean, wts = w) => {
    if (ids.length !== 2) return
    setBusy(true)
    setErr(null)
    try {
      setResult(await post<Comparison>('/compare', { vacancy_ids: ids, weights: wts, save }))
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => {
    if (ids.length === 2 && w) void run(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp.get('ids'), defaults.data])
  const saveDefaults = useAction(() => put('/compare/defaults', { weights: w }), { success: 'Saved as default weights' })
  const explain = useAction(() => post<{ summary: string; tradeoffs: string[]; recommendation: string; uncertainty: string }>('/compare/explain', { vacancy_ids: ids, weights: w, save: false }))

  if (ids.length !== 2)
    return (
      <>
        <PageHeader title="Compare" description="Compare exactly two vacancies side by side." />
        <Picker onPick={(pair) => setSp({ ids: pair.join(',') })} />
        <History items={history.data} />
      </>
    )
  return (
    <>
      <PageHeader title="Compare" crumbs={[{ label: 'Compare', to: '/compare' }, { label: 'Result' }]} description="Criterion-by-criterion, with unknowns kept visible. Missing information never counts as a win." actions={<Button variant="ghost" onClick={() => setSp({})}>Choose others</Button>} />
      {err && <Alert tone="danger">{err}</Alert>}
      {busy && !result ? <LoadingCards count={2} /> : result && (
        <div className="stack-lg">
          <div className="grid grid-2">
            {(['a', 'b'] as const).map((k) => (
              <Card key={k} className="stack-sm">
                <Badge tone={k === 'a' ? 'brand' : 'info'}>{k.toUpperCase()}</Badge>
                <h2 style={{ fontSize: 'var(--text-lg)' }}><Link to={`/vacancies/${result[k].id}`}>{result[k].title}</Link></h2>
                <span className="small secondary">{result[k].company ?? 'Company not stated'} · {humanize(result[k].status)}</span>
                <div className="row" style={{ gap: 'var(--space-4)' }}>
                  <span className="stack-sm" style={{ gap: 2 }}><span className="xs muted">Profile fit</span><Meter value={result[k].candidate_fit_score} label="Profile fit" /></span>
                  <span className="stack-sm" style={{ gap: 2 }}><span className="xs muted">Preference fit</span><Meter value={result[k].preference_fit_score} label="Preference fit" /></span>
                </div>
              </Card>
            ))}
          </div>
          <Card tone="hero" className="stack-sm">
            <strong>{result.recommendation.text}</strong>
            <span className="small">Coverage {Math.round(result.coverage * 100)}% of weighted criteria · uncertainty {result.recommendation.uncertainty}{result.unknown_criteria.length > 0 && ` · unknown: ${result.unknown_criteria.map(humanize).join(', ')}`}</span>
          </Card>
          <div className="table-wrap desktop-only">
            <table className="table">
              <caption className="sr-only">Comparison by criterion</caption>
              <thead><tr><th scope="col">Criterion</th><th scope="col">A</th><th scope="col">B</th><th scope="col">Winner</th><th scope="col">Weight</th></tr></thead>
              <tbody>
                {result.criteria.map((c) => (
                  <tr key={c.criterion}>
                    <th scope="row" style={{ position: 'static', textTransform: 'none', letterSpacing: 0, fontSize: 'var(--text-sm)', color: 'var(--foreground)' }}>{humanize(c.criterion)}<div className="xs muted" style={{ fontWeight: 400 }}>{c.note}</div></th>
                    <td className="wrap-anywhere">{fmt(c.a)}</td>
                    <td className="wrap-anywhere">{fmt(c.b)}</td>
                    <td><Badge tone={WIN_TONE[c.winner]}>{c.winner}</Badge></td>
                    <td>{w && <input aria-label={`Weight for ${humanize(c.criterion)}`} type="number" min={0} max={10} step={1} className="input" style={{ width: 72, minHeight: 36 }} value={w[c.criterion] ?? c.weight} onChange={(e) => setWeights({ ...w, [c.criterion]: Number(e.target.value) })} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="stack mobile-only">
            {result.criteria.map((c) => (
              <Card key={c.criterion} className="stack-sm">
                <div className="row-between"><strong>{humanize(c.criterion)}</strong><Badge tone={WIN_TONE[c.winner]}>{c.winner}</Badge></div>
                <dl className="kv"><dt>A</dt><dd>{fmt(c.a)}</dd><dt>B</dt><dd>{fmt(c.b)}</dd></dl>
                <span className="xs muted">{c.note}</span>
              </Card>
            ))}
          </div>
          <div className="row">
            <Button variant="primary" loading={busy} onClick={() => void run(true)}>Recalculate with these weights</Button>
            <Button onClick={() => saveDefaults.mutate(undefined)}>Save weights as default</Button>
            <Button variant="ai" icon={<Sparkles size={16} />} loading={explain.isPending} onClick={() => explain.mutate(undefined)}>Explain with AI</Button>
          </div>
          {result.tradeoffs.length > 0 && <Card><h2 style={{ fontSize: 'var(--text-lg)' }}>Trade-offs</h2><ul>{result.tradeoffs.map((t) => <li key={t}>{t}</li>)}</ul></Card>}
          {explain.data && <Card tone="soft" className="stack-sm"><strong>AI summary (does not change scores)</strong><p>{explain.data.summary}</p><p className="small">{explain.data.recommendation}</p><p className="xs muted">{explain.data.uncertainty}</p></Card>}
        </div>
      )}
    </>
  )
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return 'Unknown'
  if (typeof v === 'number') return v <= 1 ? `${Math.round(v * 100)}%` : v.toLocaleString()
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (Array.isArray(v)) return v.length ? v.join(', ') : 'None listed'
  if (typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${humanize(k)}: ${x ?? 'unknown'}`).join(' · ')
  return humanize(String(v)) === String(v).toLowerCase() ? String(v) : String(v)
}

function Picker({ onPick }: { onPick: (ids: number[]) => void }) {
  const [sel, setSel] = useState<number[]>([])
  const q = useGet<Paged<VacancyCard>>(['vacancies', 'saved-for-compare'], '/vacancies?saved=any&limit=50&sort=best_fit')
  if (q.isLoading) return <LoadingCards />
  if (q.error) return <ErrorState error={q.error} />
  if (!q.data?.items.length) return <EmptyState icon={<Columns2 size={28} />} title="Nothing to compare yet">Collect or import vacancies first.</EmptyState>
  return (
    <Card className="stack">
      <p className="small secondary">Select exactly two vacancies. A third selection is disabled.</p>
      <ul className="list-plain stack-sm">
        {q.data.items.map((v) => {
          const on = sel.includes(v.id)
          return (
            <li key={v.id}>
              <label className="checkbox" style={{ opacity: !on && sel.length >= 2 ? 0.5 : 1 }}>
                <input type="checkbox" checked={on} disabled={!on && sel.length >= 2} onChange={(e) => setSel((s) => (e.target.checked ? [...s, v.id].slice(0, 2) : s.filter((x) => x !== v.id)))} />
                {v.title} <span className="muted">· {v.company ?? 'Unknown company'}</span>
              </label>
            </li>
          )
        })}
      </ul>
      <Button variant="primary" disabled={sel.length !== 2} onClick={() => onPick(sel)}>Compare selected</Button>
    </Card>
  )
}

function History({ items }: { items?: { id: number; created_at: string; lean: string; vacancies: { id: number; title: string }[] }[] }) {
  if (!items?.length) return null
  return (
    <Card style={{ marginTop: 'var(--space-5)' }}>
      <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-3)' }}>Recent comparisons</h2>
      <ul className="list-plain stack-sm">
        {items.map((c) => (
          <li key={c.id} className="small">
            <Link to={`/compare?ids=${c.vacancies.map((v) => v.id).join(',')}`}>{c.vacancies.map((v) => v.title).join(' vs ')}</Link>
            <span className="muted"> · lean {c.lean}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export const _getForTests = get
