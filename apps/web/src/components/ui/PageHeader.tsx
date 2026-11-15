import type { ReactNode } from 'react'
import { Link } from 'react-router'

export function PageHeader({
  title,
  description,
  actions,
  crumbs,
  eyebrow,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
  crumbs?: { label: string; to?: string }[]
  eyebrow?: ReactNode
}) {
  return (
    <header className="page-header">
      {crumbs && crumbs.length > 0 && (
        <nav aria-label="Breadcrumb" className="crumbs">
          {crumbs.map((c, i) => (
            <span key={c.label}>
              {c.to ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
              {i < crumbs.length - 1 && ' / '}
            </span>
          ))}
        </nav>
      )}
      <div className="page-header-row">
        <div className="stack-sm">
          {eyebrow}
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="row">{actions}</div>}
      </div>
    </header>
  )
}
