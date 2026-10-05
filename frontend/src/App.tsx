import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import FindingsPage from './pages/FindingsPage'

// Lazy: recharts is ~350 kB and only this page uses it. Loading it
// eagerly more than doubled the main bundle.
const MetricsPage = lazy(() => import('./pages/MetricsPage'))

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/findings" replace />} />
          <Route path="/findings" element={<FindingsPage />} />
          <Route path="/findings/:jobId" element={<FindingsPage />} />
          <Route
            path="/metrics"
            element={
              <Suspense
                fallback={
                  <p className="p-10 text-center font-mono text-xs text-muted-foreground">
                    Loading charts
                  </p>
                }
              >
                <MetricsPage />
              </Suspense>
            }
          />
          <Route path="*" element={<Navigate to="/findings" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
