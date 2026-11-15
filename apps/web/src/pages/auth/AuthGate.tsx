import { Outlet } from 'react-router'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ErrorState, LoadingCards } from '@/components/ui'
import { LoginPage } from './LoginPage'
import { SetupPage } from './SetupPage'

function Gate() {
  const { state, loading, error, refresh } = useAuth()
  if (loading)
    return (
      <div className="content" style={{ maxWidth: 480 }}>
        <LoadingCards count={1} label="Checking session" />
      </div>
    )
  if (error || !state)
    return (
      <div className="content" style={{ maxWidth: 560 }}>
        <ErrorState error={error ?? new Error('The Unjobless API is not reachable.')} onRetry={() => void refresh()} />
      </div>
    )
  if (!state.bootstrapped) return <SetupPage tokenRequired={state.setup_token_required} />
  if (!state.authenticated) return <LoginPage />
  return <Outlet />
}

export function AuthGate() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  )
}
