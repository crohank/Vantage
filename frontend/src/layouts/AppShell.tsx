import { Container } from 'react-bootstrap'
import { Outlet } from 'react-router-dom'
import TopNav from '../components/TopNav'
import { DocumentsProvider } from '../context/DocumentsContext'

function AppShell() {
  return (
    <DocumentsProvider>
      <div className="app-shell min-vh-100" data-bs-theme="dark">
        <TopNav />
        <Container fluid="xxl" className="pt-3 pb-4">
          <Outlet />
        </Container>
      </div>
    </DocumentsProvider>
  )
}

export default AppShell
