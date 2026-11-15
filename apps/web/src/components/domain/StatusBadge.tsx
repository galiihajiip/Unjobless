import { Badge, type Tone } from '@/components/ui'
import { humanize } from '@/lib/format'

const VERIFICATION: Record<string, { tone: Tone; label: string }> = {
  VERIFIED_OPEN: { tone: 'success', label: 'Verified open' },
  LIKELY_OPEN: { tone: 'info', label: 'Likely open' },
  NEW_UNREVIEWED: { tone: 'neutral', label: 'New · unreviewed' },
  NEEDS_REVIEW: { tone: 'warning', label: 'Needs review' },
  POTENTIAL_LEAD: { tone: 'brand', label: 'Unverified lead' },
  STATUS_UNKNOWN: { tone: 'warning', label: 'Status unknown' },
  SOURCE_UNAVAILABLE: { tone: 'warning', label: 'Source unavailable' },
  CLOSED: { tone: 'danger', label: 'Closed' },
  EXPIRED: { tone: 'danger', label: 'Expired' },
  REJECTED_AS_IRRELEVANT: { tone: 'outline', label: 'Rejected' },
}
const FRESHNESS: Record<string, Tone> = { NEW: 'brand', ACTIVE: 'success', CLOSING_SOON: 'warning', STALE: 'neutral', EXPIRED: 'danger', UNKNOWN: 'outline' }
const HEALTH: Record<string, Tone> = { HEALTHY: 'success', DEGRADED: 'warning', FAILING: 'danger', RATE_LIMITED: 'warning', UNAVAILABLE: 'danger', UNKNOWN: 'outline' }
const ITEM: Record<string, Tone> = {
  QUEUED: 'neutral', FETCHING: 'info', EXTRACTED: 'info', NEEDS_REVIEW: 'warning', SAVED: 'success', DUPLICATE: 'outline',
  BLOCKED: 'danger', UNAVAILABLE: 'danger', FAILED: 'danger', REJECTED: 'outline',
}

export function VerificationBadge({ status, title }: { status: string; title?: string }) {
  const v = VERIFICATION[status] ?? { tone: 'neutral' as Tone, label: humanize(status) }
  return (
    <Badge tone={v.tone} dot title={title}>
      {v.label}
    </Badge>
  )
}
export function FreshnessBadge({ value }: { value: string }) {
  return <Badge tone={FRESHNESS[value] ?? 'neutral'}>{value === 'CLOSING_SOON' ? 'Closing soon' : humanize(value)}</Badge>
}
export function HealthBadge({ value, title }: { value: string; title?: string }) {
  return (
    <Badge tone={HEALTH[value] ?? 'neutral'} dot title={title}>
      {humanize(value)}
    </Badge>
  )
}
export function ItemStatusBadge({ value }: { value: string }) {
  return <Badge tone={ITEM[value] ?? 'neutral'}>{humanize(value)}</Badge>
}
export function ClassBadge({ value }: { value: string }) {
  const tone: Tone = value === 'DIRECT_VACANCY' ? 'success' : ['IRRELEVANT', 'CAREER_TREND'].includes(value) ? 'outline' : ['EMPLOYER_REVIEW', 'EMPLOYER_DISCUSSION'].includes(value) ? 'info' : 'brand'
  return <Badge tone={tone}>{humanize(value)}</Badge>
}
