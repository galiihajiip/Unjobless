import type { ReactNode } from 'react'
import { NAV } from '@/app/nav'
import { EmptyState, PageHeader } from '@/components/ui'

/** Interim page shell used until the page's backend block is implemented. */
export function PageSkeleton({ path, children, emptyTitle, emptyText }: { path: string; children?: ReactNode; emptyTitle: string; emptyText: string }) {
  const item = NAV.find((n) => n.to === path)!
  const Icon = item.icon
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      {children ?? (
        <EmptyState icon={<Icon size={28} />} title={emptyTitle}>
          {emptyText}
        </EmptyState>
      )}
    </>
  )
}
