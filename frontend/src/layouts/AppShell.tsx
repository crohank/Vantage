import { Outlet } from 'react-router-dom'
import TopNav from '../components/TopNav'
import { DocumentsProvider } from '../context/DocumentsContext'

function AppShell() {
  return (
    <DocumentsProvider>
      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <TopNav />
        <main className="flex-1">
          <div className="mx-auto w-full max-w-screen-2xl px-4 py-4 sm:py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </DocumentsProvider>
  )
}

export default AppShell
