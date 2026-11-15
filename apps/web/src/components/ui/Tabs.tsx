import type { KeyboardEvent } from 'react'

export interface TabItem<T extends string> {
  value: T
  label: string
  count?: number
}
/** Roving-tabindex tablist (WAI-ARIA tabs pattern). Panels are rendered by the caller. */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  idPrefix = 'tab',
}: {
  items: TabItem<T>[]
  value: T
  onChange: (v: T) => void
  label: string
  idPrefix?: string
}) {
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, idx: number) => {
    const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    if (!dir) return
    e.preventDefault()
    const next = items[(idx + dir + items.length) % items.length]
    if (next) {
      onChange(next.value)
      document.getElementById(`${idPrefix}-${next.value}`)?.focus()
    }
  }
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((t, i) => (
        <button
          key={t.value}
          id={`${idPrefix}-${t.value}`}
          role="tab"
          type="button"
          className="tab"
          aria-selected={t.value === value}
          aria-controls={`${idPrefix}-panel`}
          tabIndex={t.value === value ? 0 : -1}
          onClick={() => onChange(t.value)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {t.label}
          {t.count !== undefined && <span className="num muted"> {t.count}</span>}
        </button>
      ))}
    </div>
  )
}
