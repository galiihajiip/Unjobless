import type { ReactNode } from 'react'
import { useId, useState } from 'react'

/** Tooltip shown on hover and keyboard focus; content is linked with aria-describedby. */
export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  const [show, setShow] = useState(false)
  const id = useId()
  return (
    <span
      className="tooltip"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      aria-describedby={id}
    >
      {children}
      <span id={id} role="tooltip" className="tooltip-content" hidden={!show}>
        {content}
      </span>
    </span>
  )
}
