import { useInfiniteQuery } from '@tanstack/react-query'
import { Columns2, Compass, SlidersHorizontal, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { VacancyCardView } from '@/components/domain/VacancyCardView'
import { Button, Checkbox, Dialog, EmptyState, ErrorState, LoadingCards, PageHeader, Select, TextInput } from '@/components/ui'
import { get, put, qs } from '@/lib/api'
import { humanize } from '@/lib/format'
import { useAction, useGet } from '@/lib/queries'
import type { Paged, VacancyCard } from '@/lib/types'

interface Facets {
  status: Record<string, number>
  freshness: Record<string, number>
  employment_type: Record<string, number>
  work_arrangement: Record<string, number>
  cities: { city: string; count: number }[]
  skills: { skill: string; count: number }[]
  sources: { id: number; name: string }[]
}
const MULTI = ['status', 'freshness', 'employment_type', 'work_arrangement', 'city', 'skill', 'seniority'] as const
const LEVELS = [
  { value: 'any', label: 'All levels' },
  { value: 'internship', label: 'Magang / internship' },
  { value: 'early', label: 'Early career (no senior)' },
]
const SORTS = [
  { value: 'newest', label: 'Newest first' },
  { value: 'best_fit', label: 'Best profile fit' },
  { value: 'preference_fit', label: 'Best preference fit' },
  { value: 'deadline', label: 'Deadline soonest' },
  { value: 'confidence', label: 'Most complete data' },
  { value: 'relevance', label: 'Search relevance' },
]

export default function DiscoverPage() {
  const [sp, setSp] = useSearchParams()
  const navigate = useNavigate()
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [q, setQ] = useState(sp.get('q') ?? '')
  const params = useMemo(() => {
    const p: Record<string, string | string[]> = {}
    for (const [k, v] of sp.entries()) {
      if ((MULTI as readonly string[]).includes(k)) p[k] = [...((p[k] as string[]) ?? []), v]
      else p[k] = v
    }
    return p
  }, [sp])
  const query = useInfiniteQuery({
    queryKey: ['vacancies', params],
    queryFn: ({ pageParam }) => get<Paged<VacancyCard>>(`/vacancies${qs({ ...params, cursor: pageParam ?? undefined, limit: 20 })}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
  })
  const facets = useGet<Facets>(['facets'], '/vacancies/facets')
  const save = useAction(({ id, state }: { id: number; state: string | null }) => put(`/vacancies/${id}/saved`, { state }), { invalidate: [['vacancies']] })
  const items = query.data?.pages.flatMap((p) => p.items) ?? []
  const total = query.data?.pages[0]?.total ?? 0

  const setParam = (k: string, v: string | string[] | null) => {
    const next = new URLSearchParams(sp)
    next.delete(k)
    if (Array.isArray(v)) v.forEach((x) => next.append(k, x))
    else if (v) next.set(k, v)
    setSp(next, { replace: true })
  }
  const toggle = (k: string, v: string) => {
    const cur = sp.getAll(k)
    setParam(k, cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v])
  }
  const active = [...sp.entries()].filter(([k]) => !['sort', 'q'].includes(k))

  const filterPanel = facets.data && (
    <div className="stack">
      <FacetGroup label="Status" items={Object.keys(facets.data.status)} k="status" sp={sp} toggle={toggle} />
      <FacetGroup label="Freshness" items={['NEW', 'ACTIVE', 'CLOSING_SOON', 'STALE', 'UNKNOWN']} k="freshness" sp={sp} toggle={toggle} />
      <FacetGroup label="Employment type" items={Object.keys(facets.data.employment_type)} k="employment_type" sp={sp} toggle={toggle} />
      <FacetGroup label="Work arrangement" items={Object.keys(facets.data.work_arrangement)} k="work_arrangement" sp={sp} toggle={toggle} />
      <FacetGroup label="City" items={['remote', ...facets.data.cities.map((c) => c.city)]} k="city" sp={sp} toggle={toggle} raw />
      <FacetGroup label="Skills" items={facets.data.skills.slice(0, 16).map((s) => s.skill)} k="skill" sp={sp} toggle={toggle} raw />
      <Select label="Source" value={sp.get('source_id') ?? ''} onChange={(e) => setParam('source_id', e.target.value || null)} options={[{ value: '', label: 'All sources' }, ...facets.data.sources.map((s) => ({ value: String(s.id), label: s.name }))]} />
      <TextInput label="Company" value={sp.get('company') ?? ''} onChange={(e) => setParam('company', e.target.value || null)} />
      <TextInput label="Minimum pay (stated)" type="number" inputMode="numeric" value={sp.get('min_salary') ?? ''} onChange={(e) => setParam('min_salary', e.target.value || null)} hint="Vacancies without stated pay are excluded by this filter." />
      <TextInput label="Deadline before" type="date" value={sp.get('deadline_before') ?? ''} onChange={(e) => setParam('deadline_before', e.target.value || null)} />
      <Select label="Minimum data confidence" value={sp.get('min_confidence') ?? ''} onChange={(e) => setParam('min_confidence', e.target.value || null)} options={[{ value: '', label: 'Any' }, { value: '0.4', label: '40%+' }, { value: '0.6', label: '60%+' }, { value: '0.8', label: '80%+' }]} />
      <Select label="Saved" value={sp.get('saved') ?? 'hide_dismissed'} onChange={(e) => setParam('saved', e.target.value)} options={[{ value: 'hide_dismissed', label: 'Hide dismissed' }, { value: 'any', label: 'Everything' }, { value: 'saved', label: 'Saved' }, { value: 'interesting', label: 'Interesting' }, { value: 'dismissed', label: 'Dismissed' }]} />
      <Checkbox label="Include closed and expired" checked={sp.get('include_closed') === 'true'} onChange={(e) => setParam('include_closed', e.target.checked ? 'true' : null)} />
    </div>
  )

  return (
    <>
      <PageHeader
        title="Discover"
        description="Vacancies collected from your sources and imports. Unverified leads live in Opportunity Signals."
        actions={
          <Button variant="secondary" className="mobile-only" icon={<SlidersHorizontal size={16} />} onClick={() => setFiltersOpen(true)}>
            Filters{active.length ? ` (${active.length})` : ''}
          </Button>
        }
      />
      <form
        className="row"
        style={{ marginBottom: 'var(--space-4)' }}
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          setParam('q', q || null)
          if (q && !sp.get('sort')) setParam('sort', 'relevance')
        }}
      >
        <div className="search-input" style={{ flex: '1 1 260px' }}>
          <Compass size={18} aria-hidden="true" />
          <label className="sr-only" htmlFor="discover-q">Search vacancies</label>
          <input id="discover-q" className="input" placeholder="Search roles, companies, skills… e.g. magang data jakarta" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select aria-label="Level" className="select" style={{ width: 'auto', minWidth: 170 }} value={sp.get('level') ?? 'any'} onChange={(e) => setParam('level', e.target.value === 'any' ? null : e.target.value)}>
          {LEVELS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <select aria-label="Sort" className="select" style={{ width: 'auto', minWidth: 200 }} value={sp.get('sort') ?? 'newest'} onChange={(e) => setParam('sort', e.target.value)}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </form>
      {active.length > 0 && (
        <div className="chip-list" style={{ marginBottom: 'var(--space-4)' }}>
          {active.map(([k, v]) => (
            <button key={`${k}${v}`} className="badge badge-brand" style={{ border: 0, cursor: 'pointer' }} onClick={() => setParam(k, sp.getAll(k).filter((x) => x !== v))} aria-label={`Remove filter ${humanize(k)} ${v}`}>
              {humanize(k)}: {humanize(v)} <X size={12} aria-hidden="true" />
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={() => setSp(new URLSearchParams(sp.get('sort') ? { sort: sp.get('sort') as string } : {}))}>
            Clear all
          </button>
        </div>
      )}
      <div style={{ display: 'grid', gap: 'var(--space-5)', gridTemplateColumns: 'minmax(0, 1fr)' }} className="discover-grid">
        <aside className="desktop-only card" style={{ alignSelf: 'start', position: 'sticky', top: 'var(--space-4)', maxHeight: 'calc(100dvh - 32px)', overflowY: 'auto' }} aria-label="Filters">
          {filterPanel}
        </aside>
        <section className="stack" aria-live="polite" aria-busy={query.isFetching}>
          <span className="small muted num">{query.isLoading ? 'Loading…' : `${total} vacanc${total === 1 ? 'y' : 'ies'}`}</span>
          {query.isLoading ? (
            <LoadingCards count={3} />
          ) : query.error ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState icon={<Compass size={28} />} title="No vacancies match" action={<Link className="btn btn-primary" to="/import">Import a vacancy</Link>}>
              Try fewer filters, enable a source, or import a URL or pasted post.
            </EmptyState>
          ) : (
            <>
              {items.map((v) => (
                <VacancyCardView
                  key={v.id}
                  v={v}
                  onSave={(state) => save.mutate({ id: v.id, state })}
                  onDismiss={() => save.mutate({ id: v.id, state: 'DISMISSED' })}
                  selected={selected.includes(v.id)}
                  selectDisabled={selected.length >= 2}
                  onSelect={(c) => setSelected((s) => (c ? [...s, v.id].slice(0, 2) : s.filter((x) => x !== v.id)))}
                />
              ))}
              {query.hasNextPage && (
                <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                  Load more
                </Button>
              )}
            </>
          )}
        </section>
      </div>
      {selected.length > 0 && (
        <div className="card row-between" role="region" aria-label="Compare selection" style={{ position: 'sticky', bottom: 'calc(var(--bottomnav-height) + var(--space-5) + var(--safe-bottom))', marginTop: 'var(--space-4)', boxShadow: 'var(--shadow-float)', zIndex: 10 }}>
          <span className="small">
            {selected.length} of 2 selected {selected.length < 2 && <span className="muted">— pick one more to compare</span>}
          </span>
          <div className="row">
            <Button size="sm" variant="ghost" onClick={() => setSelected([])}>Clear</Button>
            <Button size="sm" variant="primary" icon={<Columns2 size={16} />} disabled={selected.length !== 2} onClick={() => navigate(`/compare?ids=${selected.join(',')}`)}>
              Compare
            </Button>
          </div>
        </div>
      )}
      <Dialog open={filtersOpen} onClose={() => setFiltersOpen(false)} title="Filters" actions={<Button variant="primary" onClick={() => setFiltersOpen(false)}>Show {total} results</Button>}>
        {filterPanel}
      </Dialog>
    </>
  )
}

function FacetGroup({ label, items, k, sp, toggle, raw }: { label: string; items: string[]; k: string; sp: URLSearchParams; toggle: (k: string, v: string) => void; raw?: boolean }) {
  if (!items.length) return null
  const cur = sp.getAll(k)
  return (
    <fieldset style={{ border: 0, padding: 0, margin: 0 }} className="stack-sm">
      <legend className="small" style={{ fontWeight: 600, marginBottom: 6 }}>{label}</legend>
      <div className="chip-list">
        {items.map((i) => (
          <button key={i} type="button" className={`badge ${cur.includes(i) ? 'badge-brand' : 'badge-outline'}`} style={{ cursor: 'pointer', minHeight: 32 }} aria-pressed={cur.includes(i)} onClick={() => toggle(k, i)}>
            {raw ? i : humanize(i)}
          </button>
        ))}
      </div>
    </fieldset>
  )
}
