import type { ReactNode } from 'react'
import { useEffect, useId, useRef, useState } from 'react'
import { Button } from './Button'

export interface MenuAction {
  label: string
  icon?: ReactNode
  onSelect: () => void
  disabled?: boolean
}
/** Menu button pattern: Enter/Space open, arrows move, Esc closes and returns focus. */
export function Menu({ label, icon, actions }: { label: string; icon: ReactNode; actions: MenuAction[] }) {
  const [open, setOpen] = useState(false)
  const btn = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const id = useId()
  useEffect(() => {
    if (!open) return
    const first = list.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')
    first?.focus()
    const onDoc = (e: MouseEvent) => {
      if (!list.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])
  const close = () => {
    setOpen(false)
    btn.current?.focus()
  }
  return (
    <div className="menu">
      <Button
        ref={btn}
        variant="ghost"
        size="sm"
        iconOnly
        icon={icon}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      />
      {open && (
        <ul
          id={id}
          ref={list}
          role="menu"
          className="menu-list"
          onKeyDown={(e) => {
            const items = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
            const i = items.indexOf(document.activeElement as HTMLButtonElement)
            if (e.key === 'Escape') close()
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              items[(i + 1) % items.length]?.focus()
            }
            if (e.key === 'ArrowUp') {
              e.preventDefault()
              items[(i - 1 + items.length) % items.length]?.focus()
            }
          }}
        >
          {actions.map((a) => (
            <li key={a.label} role="none">
              <button
                role="menuitem"
                type="button"
                className="menu-item"
                disabled={a.disabled}
                onClick={() => {
                  a.onSelect()
                  close()
                }}
              >
                {a.icon}
                {a.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
