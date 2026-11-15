import { useState } from 'react'
import { Alert, Button, TextInput } from '@/components/ui'
import { ApiError, post } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { AuthLayout } from './AuthLayout'

export function SetupPage({ tokenRequired }: { tokenRequired: boolean }) {
  const { refresh } = useAuth()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const mismatch = confirm.length > 0 && confirm !== password
  return (
    <AuthLayout title="Set up your private workspace" subtitle="This one-time step creates the only owner account for this Unjobless instance.">
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault()
          if (mismatch) return
          setBusy(true)
          setError(null)
          try {
            await post('/auth/bootstrap', { display_name: name, password, setup_token: token || null })
            await refresh()
          } catch (err) {
            setError(err instanceof ApiError ? err.message : 'Setup failed.')
          } finally {
            setBusy(false)
          }
        }}
      >
        {error && <Alert tone="danger">{error}</Alert>}
        <TextInput label="Your name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
        <TextInput label="Password" type="password" autoComplete="new-password" required minLength={12} hint="At least 12 characters. A passphrase works well." value={password} onChange={(e) => setPassword(e.target.value)} />
        <TextInput label="Confirm password" type="password" autoComplete="new-password" required value={confirm} error={mismatch ? 'Passwords do not match.' : undefined} onChange={(e) => setConfirm(e.target.value)} />
        {tokenRequired && (
          <TextInput label="Setup token" required hint="Printed by the server on first start (see the deployment guide)." value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
        )}
        <Button variant="primary" type="submit" block loading={busy} disabled={mismatch}>
          Create owner account
        </Button>
      </form>
    </AuthLayout>
  )
}
