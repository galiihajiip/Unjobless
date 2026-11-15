import { RefreshCw } from 'lucide-react'
import { useRegisterSW } from 'virtual:pwa-register/react'

/** “New version available” banner. The new service worker only takes over when the owner chooses. */
export function UpdatePrompt() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({ immediate: true })
  if (!needRefresh) return null
  return (
    <div className="toast" role="status" style={{ position: 'fixed', zIndex: 70, left: '50%', transform: 'translateX(-50%)', top: 'calc(var(--space-3) + var(--safe-top))' }}>
      <span>A new version of Unjobless is available.</span>
      <button type="button" onClick={() => void updateServiceWorker(true)} className="btn btn-sm btn-primary">
        <RefreshCw size={14} /> Update
      </button>
      <button type="button" aria-label="Later" onClick={() => setNeedRefresh(false)}>Later</button>
    </div>
  )
}
