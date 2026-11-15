import { ExternalLink, Mail } from 'lucide-react'
import { useState } from 'react'
import { Alert, Button, Dialog } from '@/components/ui'
import { get } from '@/lib/api'
import { errorMessage } from '@/lib/queries'

interface Link {
  kind: 'url' | 'email'
  destination: string
  domain: string
  note: string
}

/** Opens the original application page after showing the external destination. Never submits anything. */
export function ApplyButton({ vacancyId, disabled }: { vacancyId: number; disabled?: boolean }) {
  const [link, setLink] = useState<Link | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <>
      <Button
        variant="primary"
        icon={<ExternalLink size={16} />}
        disabled={disabled}
        loading={busy}
        onClick={async () => {
          setBusy(true)
          setErr(null)
          try {
            setLink(await get<Link>(`/vacancies/${vacancyId}/apply-link`))
          } catch (e) {
            setErr(errorMessage(e))
          } finally {
            setBusy(false)
          }
        }}
      >
        Apply on original site
      </Button>
      {err && <Alert tone="warning">{err}</Alert>}
      <Dialog
        open={!!link}
        onClose={() => setLink(null)}
        title="You are leaving Unjobless"
        description={link?.note}
        actions={
          link && (
            <>
              <Button onClick={() => setLink(null)}>Cancel</Button>
              <a
                className="btn btn-primary"
                href={link.kind === 'email' ? `mailto:${link.destination}` : link.destination}
                target="_blank"
                rel="noopener noreferrer external"
                onClick={() => setLink(null)}
              >
                {link.kind === 'email' ? <Mail size={16} /> : <ExternalLink size={16} />} Continue to {link.domain}
              </a>
            </>
          )
        }
      >
        {link && (
          <div className="stack-sm">
            <span className="small secondary">Destination</span>
            <code className="wrap-anywhere small">{link.destination}</code>
            <span className="xs muted">After applying, mark it as applied in Applications. Unjobless does not submit applications for you.</span>
          </div>
        )}
      </Dialog>
    </>
  )
}
