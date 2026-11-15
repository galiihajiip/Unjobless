import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useEffect, useId, useRef } from 'react'
import { Button } from './Button'

/** Accessible modal dialog built on the native <dialog> element (focus trap + Esc handled by the browser). */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  actions,
  sheet = true,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  actions?: ReactNode
  sheet?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descId = useId()
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) {
      if (typeof el.showModal === 'function') el.showModal()
      else el.setAttribute('open', '')
    } else if (!open && el.open) {
      if (typeof el.close === 'function') el.close()
      else el.removeAttribute('open')
    }
  }, [open])
  return (
    <dialog
      ref={ref}
      className={`dialog ${sheet ? 'sheet' : ''}`}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
    >
      {open && (
        <div className="dialog-body">
          <div className="dialog-header">
            <div className="stack-sm">
              <h2 id={titleId}>{title}</h2>
              {description && (
                <p id={descId} className="secondary small">
                  {description}
                </p>
              )}
            </div>
            <Button variant="ghost" iconOnly icon={<X size={18} />} aria-label="Close dialog" onClick={onClose} />
          </div>
          {children}
          {actions && <div className="dialog-actions">{actions}</div>}
        </div>
      )}
    </dialog>
  )
}
