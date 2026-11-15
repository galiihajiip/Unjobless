import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { forwardRef } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'ai' | 'danger'
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'md' | 'sm'
  icon?: ReactNode
  iconOnly?: boolean
  loading?: boolean
  block?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', icon, iconOnly, loading, block, className = '', children, disabled, type = 'button', ...rest },
  ref,
) {
  const cls = ['btn', `btn-${variant}`, size === 'sm' && 'btn-sm', iconOnly && 'btn-icon', block && 'btn-block', className]
    .filter(Boolean)
    .join(' ')
  return (
    <button ref={ref} type={type} className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="spinner" aria-hidden="true" /> : icon}
      {iconOnly ? null : children}
    </button>
  )
})
