export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return 'Unknown'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, withTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' })
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  const abs = Math.abs(diff)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [u, s] of units) if (abs >= s) return rtf.format(-Math.round(diff / s), u)
  return 'just now'
}

export function humanize(enumValue: string | null | undefined): string {
  if (!enumValue) return 'Unknown'
  return enumValue
    .toLowerCase()
    .split('_')
    .map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ')
}

export function fmtMoney(min: number | null | undefined, max: number | null | undefined, currency?: string | null, period?: string | null): string {
  if (min == null && max == null) return 'Not stated'
  const f = (n: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(n)
  const range = min != null && max != null && min !== max ? `${f(min)}–${f(max)}` : f((min ?? max) as number)
  const per = period && period !== 'UNKNOWN' ? ` / ${period.toLowerCase()}` : ''
  return `${currency ?? ''} ${range}${per}`.trim()
}

export function domainOf(url: string | null | undefined): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}
