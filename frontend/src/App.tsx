import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import AnalysePage from './pages/AnalysePage'
import DocumentsPage from './pages/DocumentsPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/analyse" replace />} />
          <Route path="/analyse" element={<AnalysePage />} />
          <Route path="/analyse/:analysisId" element={<AnalysePage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:documentId" element={<DocumentsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
