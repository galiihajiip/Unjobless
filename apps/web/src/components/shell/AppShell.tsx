import { LogOut, Menu as MenuIcon, WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { GROUPS, MOBILE_PRIMARY, NAV } from '@/app/nav'
import { Dialog } from '@/components/ui'
import { useAuth } from '@/lib/auth'
import { Brand } from './Brand'
import { UpdatePrompt } from './UpdatePrompt'

function useOnline() {
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

export function AppShell() {
  const location = useLocation()
  // The sheet is tied to the path it was opened on, so navigating closes it without an effect.
  const [moreOpenAt, setMoreOpenAt] = useState<string | null>(null)
  const moreOpen = moreOpenAt === location.pathname
  const setMoreOpen = (v: boolean) => setMoreOpenAt(v ? location.pathname : null)
  const online = useOnline()
  const { logout } = useAuth()
  const current = NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to)))
  const moreActive = current ? !MOBILE_PRIMARY.includes(current.to) : false

  return (
    <div className="shell">
      {import.meta.env.PROD && <UpdatePrompt />}
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar" aria-label="Main navigation">
        <Brand />
        <nav className="nav">
          {GROUPS.map((g) => (
            <div key={g} className="nav">
              <div className="nav-section">{g}</div>
              {NAV.filter((n) => n.group === g).map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === '/'} className="nav-link" title={n.label}>
                  <n.icon size={20} aria-hidden="true" />
                  <span className="nav-label">{n.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div style={{ marginTop: 'auto' }}>
          <button type="button" className="nav-link" style={{ border: 0, background: 'transparent', width: '100%', cursor: 'pointer' }} onClick={() => void logout()} title="Sign out">
            <LogOut size={20} aria-hidden="true" />
            <span className="nav-label">Sign out</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar mobile-only">
          <Brand />
          <span className="small secondary truncate">{current?.label}</span>
        </header>
        {!online && (
          <div className="content" style={{ paddingBottom: 0 }}>
            <div className="alert alert-warning" role="status">
              <WifiOff size={18} aria-hidden="true" /> You are offline. Showing what is already loaded; changes need a connection.
            </div>
          </div>
        )}
        <main id="main" className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <nav className="bottom-nav" aria-label="Primary">
        {NAV.filter((n) => MOBILE_PRIMARY.includes(n.to)).map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'}>
            <n.icon size={20} aria-hidden="true" />
            <span>{n.label === 'My Career Profile' ? 'Profile' : n.label}</span>
          </NavLink>
        ))}
        <button type="button" aria-haspopup="dialog" aria-expanded={moreOpen} aria-current={moreActive ? 'page' : undefined} onClick={() => setMoreOpen(true)}>
          <MenuIcon size={20} aria-hidden="true" />
          <span>More</span>
        </button>
      </nav>

      <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title="All sections">
        <nav className="nav" aria-label="All sections">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'} className="nav-link">
              <n.icon size={20} aria-hidden="true" />
              <span className="nav-label">
                {n.label}
                <span className="xs muted" style={{ display: 'block', fontWeight: 400 }}>
                  {n.description}
                </span>
              </span>
            </NavLink>
          ))}
          <button type="button" className="nav-link" style={{ border: 0, background: 'transparent', cursor: 'pointer' }} onClick={() => void logout()}>
            <LogOut size={20} aria-hidden="true" />
            <span className="nav-label">Sign out</span>
          </button>
        </nav>
      </Dialog>
    </div>
  )
}
