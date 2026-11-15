import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { createContext, useCallback, useContext, useMemo, useState } from 'react'

interface ToastItem {
  id: number
  message: string
}
const ToastCtx = createContext<{ notify: (message: string) => void }>({ notify: () => {} })

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((t) => t.id !== id)), [])
  const notify = useCallback(
    (message: string) => {
      const id = Date.now() + Math.random()
      setItems((xs) => [...xs.slice(-3), { id, message }])
      window.setTimeout(() => dismiss(id), 5000)
    },
    [dismiss],
  )
  const value = useMemo(() => ({ notify }), [notify])
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div className="toast" key={t.id}>
            <span style={{ flex: 1 }}>{t.message}</span>
            <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(t.id)}>
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
