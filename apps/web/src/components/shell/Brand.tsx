import { Link } from 'react-router'

export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 64 64" width={size * 0.6} height={size * 0.6}>
        <path d="M18 14v20a14 14 0 0 0 28 0V14" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" />
        <circle cx="32" cy="54" r="4" fill="#fff" />
      </svg>
    </span>
  )
}

export function Brand() {
  return (
    <Link to="/" className="brand" aria-label="Unjobless home">
      <BrandMark />
      <span className="brand-name">Unjobless</span>
    </Link>
  )
}
