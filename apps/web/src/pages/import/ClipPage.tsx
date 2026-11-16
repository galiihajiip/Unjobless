import { ClipboardPaste } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Alert, Button, Card, PageHeader, TextArea, TextInput } from '@/components/ui'
import { post } from '@/lib/api'
import { domainOf } from '@/lib/format'
import { errorMessage } from '@/lib/queries'
import type { ImportBatch } from '@/lib/types'

interface Clip {
  type: 'unjobless-clip'
  url: string
  title: string
  text: string
}

function isClip(d: unknown): d is Clip {
  const c = d as Clip
  return !!c && c.type === 'unjobless-clip' && typeof c.url === 'string' && typeof c.text === 'string' && typeof c.title === 'string'
}

/**
 * Receives the page the owner is viewing in their own browser (sent by the bookmarklet via
 * postMessage from the opener window). Nothing is saved until the owner clicks Import.
 */
export default function ClipPage() {
  const navigate = useNavigate()
  const [clip, setClip] = useState<Clip | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      // Only accept data from the window that opened this one (the page the owner clicked the bookmark on).
      if (!window.opener || e.source !== window.opener || !isClip(e.data)) return
      const d = e.data
      setClip({ ...d, url: d.url.slice(0, 2048), title: d.title.slice(0, 300) })
      setText(d.text.slice(0, 190_000))
      ;(e.source as Window).postMessage('unjobless-clip-received', e.origin)
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [])

  const submit = async () => {
    if (!clip) return
    setBusy(true)
    setErr(null)
    try {
      const r = await post<{ batch: ImportBatch }>('/imports/paste', {
        records: [{ text: `${clip.title}\n\n${text}`, source_url: /^https?:\/\//.test(clip.url) ? clip.url : null, platform: domainOf(clip.url) || 'browser clip' }],
        note: 'Browser clip',
      })
      navigate(`/import/batches/${r.batch.id}`)
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="Clip from browser" description="The page you were viewing is shown below. Check it, then import it for review." />
      {!clip ? (
        <Alert tone="info" title="Waiting for a page…">
          Open a job page in your browser and click the “Send to Unjobless” bookmark. Install it from Import Center › Paste content.
        </Alert>
      ) : (
        <Card className="stack">
          <TextInput label="Page" value={clip.title} readOnly />
          <TextInput label="Source URL" value={clip.url} readOnly />
          <TextArea label="Captured text (you can trim it)" rows={14} value={text} onChange={(e) => setText(e.target.value)} hint="Tip: select just the job description before clicking the bookmark to capture only that part." />
          {err && <Alert tone="danger">{err}</Alert>}
          <Button variant="primary" icon={<ClipboardPaste size={16} />} loading={busy} disabled={!text.trim()} onClick={() => void submit()} style={{ alignSelf: 'flex-start' }}>
            Import for review
          </Button>
        </Card>
      )}
    </>
  )
}
