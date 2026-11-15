import type { ReactNode } from 'react'

export type Tone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'outline'
export function Badge({ tone = 'neutral', dot, children, title }: { tone?: Tone; dot?: boolean; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${tone !== 'neutral' ? `badge-${tone}` : ''}`} title={title}>
      {dot && <span className="dot" aria-hidden="true" />}
      {children}
    </span>
  )
}
