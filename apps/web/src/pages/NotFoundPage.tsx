import { SearchX } from 'lucide-react'
import { Link } from 'react-router'
import { EmptyState } from '@/components/ui'

export function NotFoundPage() {
  return (
    <EmptyState icon={<SearchX size={28} />} title="Page not found" action={<Link className="btn btn-secondary" to="/">Back to overview</Link>}>
      This page does not exist in your Unjobless workspace.
    </EmptyState>
  )
}
