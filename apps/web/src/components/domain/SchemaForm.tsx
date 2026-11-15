import { Checkbox, TextArea, TextInput } from '@/components/ui'
import { humanize } from '@/lib/format'
import type { JsonSchema } from '@/lib/types'

/** Minimal JSON-schema form for connector configs: strings, numbers, booleans, string lists; anything else as JSON. */
export function SchemaForm({ schema, value, onChange }: { schema: JsonSchema; value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const props = schema.properties ?? {}
  return (
    <div className="stack">
      {Object.entries(props).map(([key, s]) => {
        const type = s.type ?? s.anyOf?.find((x) => x.type && x.type !== 'null')?.type
        const label = s.title ?? humanize(key)
        const v = value[key] ?? s.default
        const required = schema.required?.includes(key)
        if (type === 'boolean') return <Checkbox key={key} label={label} checked={Boolean(v)} onChange={(e) => onChange({ ...value, [key]: e.target.checked })} />
        if (type === 'integer' || type === 'number')
          return <TextInput key={key} label={label} type="number" required={required} hint={s.description} value={v == null ? '' : String(v)} onChange={(e) => onChange({ ...value, [key]: e.target.value === '' ? undefined : Number(e.target.value) })} />
        if (type === 'array' && (s.items?.type === 'string' || !s.items?.$ref))
          if (s.items?.type === 'string')
            return <TextArea key={key} label={`${label} (one per line)`} hint={s.description} value={((v as string[]) ?? []).join('\n')} onChange={(e) => onChange({ ...value, [key]: e.target.value.split('\n').map((x) => x.trim()).filter(Boolean) })} />
        if (type === 'string' || !type)
          return <TextInput key={key} label={label} required={required} hint={s.description} value={(v as string) ?? ''} onChange={(e) => onChange({ ...value, [key]: e.target.value || undefined })} />
        return (
          <TextArea key={key} label={`${label} (JSON)`} className="mono" hint={s.description} defaultValue={JSON.stringify(v ?? [], null, 1)} onChange={(e) => { try { onChange({ ...value, [key]: JSON.parse(e.target.value) }) } catch { /* keep typing */ } }} />
        )
      })}
    </div>
  )
}
