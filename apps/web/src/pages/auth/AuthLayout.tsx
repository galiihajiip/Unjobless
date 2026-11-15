import type { ReactNode } from 'react'
import { BrandMark } from '@/components/shell/Brand'

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <main id="main" style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', padding: 'calc(16px + var(--safe-top)) 16px calc(16px + var(--safe-bottom))' }}>
      <div className="card stack-lg" style={{ width: 'min(440px, 100%)', padding: 'var(--space-6)' }}>
        <div className="stack" style={{ alignItems: 'center', textAlign: 'center' }}>
          <BrandMark size={52} />
          <span className="badge badge-brand">Unjobless</span>
          <h1 style={{ fontSize: 'var(--text-2xl)' }}>{title}</h1>
          <p className="secondary">{subtitle}</p>
        </div>
        {children}
      </div>
    </main>
  )
}
