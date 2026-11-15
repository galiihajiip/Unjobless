import { Apple, Monitor, Smartphone } from 'lucide-react'
import { Alert, Card, PageHeader } from '@/components/ui'

export default function InstallHelpPage() {
  return (
    <>
      <PageHeader crumbs={[{ label: 'Settings', to: '/settings' }, { label: 'Install' }]} title="Install Unjobless" description="Unjobless is a web app you can install like a native app. It needs your instance to be served over HTTPS." />
      <div className="grid grid-3">
        <Card className="stack-sm">
          <h2 className="row" style={{ fontSize: 'var(--text-lg)' }}><Apple size={20} aria-hidden="true" /> iPhone & iPad</h2>
          <ol className="small stack-sm" style={{ paddingLeft: '1.2em', margin: 0 }}>
            <li>Open your Unjobless address in <strong>Safari</strong>.</li>
            <li>Tap the <strong>Share</strong> button.</li>
            <li>Choose <strong>Add to Home Screen</strong>, then <strong>Add</strong>.</li>
          </ol>
          <p className="xs muted">On iOS, installed web apps keep their own sign-in. Background notifications depend on your iOS version and are not guaranteed; in-app reminders always work.</p>
        </Card>
        <Card className="stack-sm">
          <h2 className="row" style={{ fontSize: 'var(--text-lg)' }}><Smartphone size={20} aria-hidden="true" /> Android</h2>
          <ol className="small stack-sm" style={{ paddingLeft: '1.2em', margin: 0 }}>
            <li>Open Unjobless in <strong>Chrome</strong> (or Edge/Samsung Internet).</li>
            <li>Tap the menu <strong>⋮</strong> and choose <strong>Install app</strong> or <strong>Add to Home screen</strong>.</li>
            <li>Confirm. Unjobless opens in its own window.</li>
          </ol>
        </Card>
        <Card className="stack-sm">
          <h2 className="row" style={{ fontSize: 'var(--text-lg)' }}><Monitor size={20} aria-hidden="true" /> Mac, Windows & Linux</h2>
          <ol className="small stack-sm" style={{ paddingLeft: '1.2em', margin: 0 }}>
            <li><strong>Chrome/Edge:</strong> click the install icon in the address bar, or menu › <strong>Install Unjobless</strong>.</li>
            <li><strong>Safari on macOS:</strong> File › <strong>Add to Dock</strong>.</li>
            <li><strong>Firefox:</strong> desktop install is not supported; use it as a normal tab.</li>
          </ol>
        </Card>
      </div>
      <Alert tone="info" title="Offline behaviour">After one visit the app shell opens offline and shows a clear offline banner. Your CVs, vacancies and AI results are never stored in the offline cache — they load only when you are connected and signed in.</Alert>
    </>
  )
}
