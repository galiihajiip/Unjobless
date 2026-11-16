import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { makeQueryClient, routes } from '@/App'
import { ToastProvider } from '@/components/ui'
import { bookmarkletCode } from './ImportPage'

vi.mock('virtual:pwa-register/react', () => ({ useRegisterSW: () => ({ needRefresh: [false, () => {}], offlineReady: [false, () => {}], updateServiceWorker: async () => {} }) }))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ bootstrapped: true, authenticated: true, setup_token_required: false }), { headers: { 'content-type': 'application/json' } })))
})
afterEach(() => vi.unstubAllGlobals())

function renderClip() {
  const router = createMemoryRouter(routes, { initialEntries: ['/import/clip'] })
  render(<QueryClientProvider client={makeQueryClient()}><ToastProvider><RouterProvider router={router} /></ToastProvider></QueryClientProvider>)
}

test('accepts a clip only from the opener window', async () => {
  const opener = { postMessage: vi.fn() } as unknown as Window
  Object.defineProperty(window, 'opener', { value: opener, configurable: true })
  renderClip()
  expect(await screen.findByText('Waiting for a page…')).toBeInTheDocument()
  const data = { type: 'unjobless-clip', url: 'https://glints.com/id/opportunities/jobs/x', title: 'Data Intern', text: 'Magang Data Analyst di PT Contoh' }
  act(() => { window.dispatchEvent(new MessageEvent('message', { data, source: window })) }) // not the opener → ignored
  expect(screen.queryByDisplayValue('Data Intern')).toBeNull()
  act(() => { window.dispatchEvent(new MessageEvent('message', { data, source: opener, origin: 'https://glints.com' })) })
  expect(await screen.findByDisplayValue('Data Intern')).toBeInTheDocument()
  expect(opener.postMessage).toHaveBeenCalledWith('unjobless-clip-received', 'https://glints.com')
})

test('bookmarklet targets this origin only', () => {
  const code = decodeURIComponent(bookmarkletCode('https://jobs.example.com'))
  expect(code.startsWith('javascript:')).toBe(true)
  expect(code).toContain('"https://jobs.example.com"')
  expect(code).toContain("w.postMessage(d,O)")
})
