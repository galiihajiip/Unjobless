import { Bookmark, BookmarkCheck, Building2, CalendarClock, EyeOff, MapPin, Sparkles } from 'lucide-react'
import { Link } from 'react-router'
import { Badge, Button, Card, Checkbox } from '@/components/ui'
import { fmtDate, fmtMoney, fmtRelative, humanize } from '@/lib/format'
import type { VacancyCard } from '@/lib/types'
import { FreshnessBadge, VerificationBadge } from './StatusBadge'
import { ScoreRow } from './Scores'

export function VacancyCardView({
  v,
  onSave,
  onDismiss,
  selected,
  onSelect,
  selectDisabled,
}: {
  v: VacancyCard
  onSave?: (state: string | null) => void
  onDismiss?: () => void
  selected?: boolean
  onSelect?: (checked: boolean) => void
  selectDisabled?: boolean
}) {
  const saved = v.saved_state === 'SAVED' || v.saved_state === 'INTERESTING'
  return (
    <Card className="stack">
      <div className="row-between" style={{ alignItems: 'flex-start' }}>
        <div className="stack-sm" style={{ minWidth: 0, flex: 1 }}>
          <div className="row" style={{ gap: 6 }}>
            <VerificationBadge status={v.verification_status} title={v.status_reason ?? undefined} />
            <FreshnessBadge value={v.freshness} />
            {v.employment_type !== 'UNKNOWN' && <Badge>{humanize(v.employment_type)}</Badge>}
            {v.application_status && <Badge tone="info">Tracked · {humanize(v.application_status)}</Badge>}
          </div>
          <h3 className="wrap-anywhere">
            <Link to={`/vacancies/${v.id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
              {v.title}
            </Link>
          </h3>
          <div className="row small secondary" style={{ gap: 'var(--space-3)' }}>
            {v.company && (
              <span className="row" style={{ gap: 4 }}>
                <Building2 size={14} aria-hidden="true" />
                {v.company}
              </span>
            )}
            <span className="row" style={{ gap: 4 }}>
              <MapPin size={14} aria-hidden="true" />
              {v.location ?? (v.work_arrangement === 'REMOTE' ? 'Remote' : 'Location unknown')}
              {v.work_arrangement !== 'UNKNOWN' && v.work_arrangement !== 'REMOTE' && ` · ${humanize(v.work_arrangement)}`}
            </span>
            {v.application_deadline && (
              <span className="row num" style={{ gap: 4 }}>
                <CalendarClock size={14} aria-hidden="true" />
                Deadline {fmtDate(v.application_deadline)}
              </span>
            )}
          </div>
        </div>
        <div className="row" style={{ gap: 4 }}>
          {onSave && (
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              icon={saved ? <BookmarkCheck size={18} /> : <Bookmark size={18} />}
              aria-label={saved ? 'Remove from saved' : 'Save vacancy'}
              aria-pressed={saved}
              onClick={() => onSave(saved ? null : 'SAVED')}
            />
          )}
          {onDismiss && <Button variant="ghost" size="sm" iconOnly icon={<EyeOff size={18} />} aria-label="Dismiss" onClick={onDismiss} />}
        </div>
      </div>
      <div className="row-between">
        <span className="small num">{v.salary_min != null || v.salary_max != null ? fmtMoney(v.salary_min, v.salary_max, v.salary_currency, v.pay_period) : <span className="muted">Pay not stated</span>}</span>
        {v.eligible === false && <Badge tone="danger">Eligibility issue</Badge>}
      </div>
      <ScoreRow cfit={v.candidate_fit_score} pfit={v.preference_fit_score} conf={v.data_confidence} />
      <div className="row-between xs muted">
        <span>
          {v.sources.length > 0 ? `${v.sources.map((s) => s.domain ?? s.name).filter((x, i, a) => a.indexOf(x) === i).join(', ')}` : 'Unknown source'} · found {fmtRelative(v.first_seen_at)}
          {v.last_checked_at && ` · checked ${fmtRelative(v.last_checked_at)}`}
        </span>
        {onSelect && <Checkbox label="Compare" checked={!!selected} disabled={selectDisabled && !selected} onChange={(e) => onSelect(e.target.checked)} />}
      </div>
      {v.warnings.length > 0 && (
        <span className="xs muted row" style={{ gap: 4 }}>
          <Sparkles size={12} aria-hidden="true" /> {v.warnings[0]}
        </span>
      )}
    </Card>
  )
}
