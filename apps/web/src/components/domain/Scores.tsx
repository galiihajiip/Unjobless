import { Meter, Tooltip } from '@/components/ui'

export function ScoreRow({ cfit, pfit, conf }: { cfit: number | null; pfit: number | null; conf: number | null }) {
  return (
    <div className="row small" style={{ gap: 'var(--space-4)' }}>
      <Tooltip content="How well your confirmed profile covers the requirements">
        <span className="stack-sm" style={{ gap: 2 }}>
          <span className="xs muted">Profile fit</span>
          <Meter value={cfit} label="Profile fit" />
        </span>
      </Tooltip>
      <Tooltip content="How well it matches your preferences">
        <span className="stack-sm" style={{ gap: 2 }}>
          <span className="xs muted">Preference fit</span>
          <Meter value={pfit} label="Preference fit" />
        </span>
      </Tooltip>
      <Tooltip content="How complete and reliable this record is">
        <span className="stack-sm" style={{ gap: 2 }}>
          <span className="xs muted">Data confidence</span>
          <Meter value={conf} label="Data confidence" />
        </span>
      </Tooltip>
    </div>
  )
}
