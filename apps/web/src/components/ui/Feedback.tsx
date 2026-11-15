import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'

export function Skeleton({ height = 16, width = '100%', style }: { height?: number | string; width?: number | string; style?: CSSProperties }) {
  return <div className="skeleton" style={{ height, width, ...style }} aria-hidden="true" />
}

export function LoadingCards({ count = 3, label = 'Loading' }: { count?: number; label?: string }) {
  return (
    <div className="stack" role="status" aria-live="polite">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: count }, (_, i) => (
        <div className="card stack-sm" key={i}>
          <Skeleton height={18} width="40%" />
          <Skeleton height={14} width="75%" />
          <Skeleton height={14} width="60%" />
        </div>
      ))}
    </div>
  )
}

export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card empty">
      <div className="icon-bubble" aria-hidden="true">
        {icon}
      </div>
      <h2 style={{ fontSize: 'var(--text-lg)' }}>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

const icons = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle }
export function Alert({ tone = 'info', title, children }: { tone?: keyof typeof icons; title?: string; children?: ReactNode }) {
  const Icon = icons[tone]
  return (
    <div className={`alert alert-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon size={18} aria-hidden="true" />
      <div className="stack-sm" style={{ gap: 2 }}>
        {title && <strong>{title}</strong>}
        {children && <div>{children}</div>}
      </div>
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <Alert tone="danger" title="Could not load this data">
      <div className="row">
        <span>{msg}</span>
        {onRetry && (
          <button type="button" className="btn btn-sm btn-secondary" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </Alert>
  )
}

export function Meter({ value, label }: { value: number | null | undefined; label: string }) {
  if (value === null || value === undefined)
    return (
      <span className="score muted" aria-label={`${label}: unknown`}>
        Unknown
      </span>
    )
  const pct = Math.round(value * 100)
  return (
    <span className="score" aria-label={`${label}: ${pct} out of 100`}>
      <span className="meter" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </span>
      {pct}
    </span>
  )
}
