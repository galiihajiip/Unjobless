import { useState } from 'react'
import { Alert, Button, TextInput } from '@/components/ui'
import { ApiError, post } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { AuthLayout } from './AuthLayout'

export function LoginPage() {
  const { refresh } = useAuth()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <AuthLayout title="Welcome back" subtitle="Discover broadly. Understand deeply. Apply deliberately.">
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          setError(null)
          try {
            await post('/auth/login', { password })
            await refresh()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : 'Sign-in failed.')
          } finally {
            setBusy(false)
          }
        }}
      >
        {error && <Alert tone="danger">{error}</Alert>}
        <TextInput label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        <Button variant="primary" type="submit" block loading={busy}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
