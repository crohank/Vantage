import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import FindingsPage from './pages/FindingsPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/findings" replace />} />
          <Route path="/findings" element={<FindingsPage />} />
          <Route path="/findings/:jobId" element={<FindingsPage />} />
          <Route path="*" element={<Navigate to="/findings" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
