import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { AppShell } from '@/components/shell/AppShell'
import { LoadingCards, ToastProvider } from '@/components/ui'
import { AuthGate } from '@/pages/auth/AuthGate'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ApiError } from '@/lib/api'

const OverviewPage = lazy(() => import('@/pages/overview/OverviewPage'))
const DiscoverPage = lazy(() => import('@/pages/discover/DiscoverPage'))
const VacancyDetailPage = lazy(() => import('@/pages/discover/VacancyDetailPage'))
const SignalsPage = lazy(() => import('@/pages/signals/SignalsPage'))
const ComparePage = lazy(() => import('@/pages/compare/ComparePage'))
const ApplicationsPage = lazy(() => import('@/pages/applications/ApplicationsPage'))
const ProfilePage = lazy(() => import('@/pages/profile/ProfilePage'))
const ImportPage = lazy(() => import('@/pages/import/ImportPage'))
const ImportBatchPage = lazy(() => import('@/pages/import/ImportBatchPage'))
const ClipPage = lazy(() => import('@/pages/import/ClipPage'))
const SourcesPage = lazy(() => import('@/pages/sources/SourcesPage'))
const SourceDetailPage = lazy(() => import('@/pages/sources/SourceDetailPage'))
const IntelligencePage = lazy(() => import('@/pages/intelligence/IntelligencePage'))
const AIStudioPage = lazy(() => import('@/pages/ai/AIStudioPage'))
const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'))
const TailorPage = lazy(() => import('@/pages/applications/TailorPage'))
const InstallHelpPage = lazy(() => import('@/pages/settings/InstallHelpPage'))

const page = (el: React.ReactNode) => <Suspense fallback={<LoadingCards count={2} />}>{el}</Suspense>

export const routes = [
  {
    element: <AuthGate />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: page(<OverviewPage />) },
          { path: 'discover', element: page(<DiscoverPage />) },
          { path: 'vacancies/:id', element: page(<VacancyDetailPage />) },
          { path: 'signals', element: page(<SignalsPage />) },
          { path: 'compare', element: page(<ComparePage />) },
          { path: 'applications', element: page(<ApplicationsPage />) },
          { path: 'applications/tailor/:vacancyId', element: page(<TailorPage />) },
          { path: 'profile', element: page(<ProfilePage />) },
          { path: 'import', element: page(<ImportPage />) },
          { path: 'import/batches/:id', element: page(<ImportBatchPage />) },
          { path: 'import/clip', element: page(<ClipPage />) },
          { path: 'sources', element: page(<SourcesPage />) },
          { path: 'sources/:id', element: page(<SourceDetailPage />) },
          { path: 'intelligence', element: page(<IntelligencePage />) },
          { path: 'ai', element: page(<AIStudioPage />) },
          { path: 'settings', element: page(<SettingsPage />) },
          { path: 'settings/install', element: page(<InstallHelpPage />) },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      },
    },
  })
}

const router = typeof window !== 'undefined' ? createBrowserRouter(routes) : null
const queryClient = makeQueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{router && <RouterProvider router={router} />}</ToastProvider>
    </QueryClientProvider>
  )
}
