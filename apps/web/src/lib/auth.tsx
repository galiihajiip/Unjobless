import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { createContext, useCallback, useContext, useEffect, useMemo } from 'react'
import { get, onUnauthorized, post } from './api'

export interface AuthState {
  bootstrapped: boolean
  authenticated: boolean
  setup_token_required: boolean
  display_name?: string | null
}
interface AuthCtx {
  state: AuthState | undefined
  loading: boolean
  error: unknown
  refresh: () => Promise<unknown>
  logout: () => Promise<void>
}
const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['auth-state'], queryFn: () => get<AuthState>('/auth/state'), staleTime: 60_000, retry: 1 })
  const refresh = q.refetch
  useEffect(() => onUnauthorized(() => void refresh()), [refresh])
  const logout = useCallback(async () => {
    try {
      await post('/auth/logout')
    } finally {
      qc.clear()
      await refresh()
    }
  }, [qc, refresh])
  const value = useMemo(
    () => ({ state: q.data, loading: q.isLoading, error: q.error, refresh, logout }),
    [q.data, q.isLoading, q.error, refresh, logout],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}
