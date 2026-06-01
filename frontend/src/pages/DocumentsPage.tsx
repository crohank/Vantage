import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Upload } from 'lucide-react'
import DocumentContent from '../components/DocumentContent'
import DocumentTabBar from '../components/DocumentTabBar'
import DocumentTree from '../components/DocumentTree'
import StatusBar from '../components/StatusBar'
import { Button } from '../components/ui/button'
import { Card } from '../components/ui/card'
import { fetchDocumentById, fetchDocuments, DocumentRecord } from '../services/api'
import { useDocumentsContext } from '../context/DocumentsContext'

function DocumentsPage() {
  const { documentId } = useParams()
  const navigate = useNavigate()
  const { openDocument, activeDocId } = useDocumentsContext()
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchDocuments({ limit: 200 })
      .then(setDocuments)
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!documentId) return
    fetchDocumentById(documentId).then(openDocument).catch(() => undefined)
  }, [documentId, openDocument])

  const onOpen = async (id: string) => {
    const doc = await fetchDocumentById(id)
    openDocument(doc)
    navigate(`/documents/${id}`)
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
      {/* Tree pane */}
      <aside className="lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)]">
        <Card className="flex h-full flex-col overflow-hidden">
          <div className="flex flex-1 flex-col">
            <DocumentTree
              documents={documents}
              search={search}
              setSearch={setSearch}
              onOpen={onOpen}
              activeId={activeDocId}
            />
          </div>
          <div className="border-t border-border p-3">
            <Button variant="outline" size="sm" className="w-full" disabled>
              <Upload size={12} />
              Upload PDF
            </Button>
          </div>
        </Card>
      </aside>

      {/* Viewer pane */}
      <section>
        <Card className="overflow-hidden">
          <DocumentTabBar />
          <div className="p-4">
            <DocumentContent />
          </div>
          <StatusBar />
        </Card>
      </section>
    </div>
  )
}

export default DocumentsPage
