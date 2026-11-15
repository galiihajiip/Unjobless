import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes, makeQueryClient } from './App'
import { ToastProvider } from './components/ui'
import { NAV } from './app/nav'

function mockApi(state: { bootstrapped: boolean; authenticated: boolean }) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url === '/api/auth/state')
        return new Response(JSON.stringify({ ...state, setup_token_required: false }), { headers: { 'content-type': 'application/json' } })
      return new Response(JSON.stringify({ items: [], total: 0 }), { headers: { 'content-type': 'application/json' } })
    }),
  )
}

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

test('shows setup when no owner exists', async () => {
  mockApi({ bootstrapped: false, authenticated: false })
  renderAt('/')
  expect(await screen.findByText('Set up your private workspace')).toBeInTheDocument()
})

test('shows login when not authenticated', async () => {
  mockApi({ bootstrapped: true, authenticated: false })
  renderAt('/discover')
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
})

test('authenticated shell exposes every section in navigation with active state', async () => {
  mockApi({ bootstrapped: true, authenticated: true })
  renderAt('/sources')
  const nav = await screen.findByRole('complementary', { name: 'Main navigation' })
  for (const item of NAV) expect(within(nav).getByRole('link', { name: item.label })).toBeInTheDocument()
  expect(within(nav).getByRole('link', { name: 'Sources' })).toHaveAttribute('aria-current', 'page')
})

test('unknown route renders not found', async () => {
  mockApi({ bootstrapped: true, authenticated: true })
  renderAt('/nope')
  expect(await screen.findByText('Page not found')).toBeInTheDocument()
})
