import type { HTMLAttributes, ReactNode } from 'react'

export function Card({
  tone = 'default',
  className = '',
  ...rest
}: HTMLAttributes<HTMLDivElement> & { tone?: 'default' | 'soft' | 'hero' }) {
  const cls = ['card', tone === 'soft' && 'card-soft', tone === 'hero' && 'card-hero', className].filter(Boolean).join(' ')
  return <div className={cls} {...rest} />
}

export function CardTitle({ title, action, as: Tag = 'h2' }: { title: ReactNode; action?: ReactNode; as?: 'h2' | 'h3' }) {
  return (
    <div className="card-title">
      <Tag style={{ fontSize: 'var(--text-lg)' }}>{title}</Tag>
      {action}
    </div>
  )
}
