import { Alert, Tabs, Tab } from 'react-bootstrap'
import { resolveDocumentUrl } from '../services/api'
import { useDocumentsContext } from '../context/DocumentsContext'

function DocumentContent() {
  const { openDocs, activeDocId } = useDocumentsContext()
  const doc = openDocs.find((d) => d.id === activeDocId) || null
  if (!doc) return <Alert variant="secondary">Select a document from the tree.</Alert>
  const pdfUrl = resolveDocumentUrl(doc.file_url) || resolveDocumentUrl(`/api/documents/${doc.id}/pdf`)
  return (
    <Tabs defaultActiveKey="pdf">
      <Tab eventKey="pdf" title="PDF">
        <iframe src={pdfUrl || ''} title={doc.id} style={{ width: '100%', height: '65vh', border: 0 }} />
      </Tab>
      <Tab eventKey="text" title="Text">
        <div className="p-2 document-text-preview">{doc.preview_text || 'No extracted text available.'}</div>
      </Tab>
      <Tab eventKey="meta" title="Metadata">
        <pre className="small">{JSON.stringify(doc, null, 2)}</pre>
      </Tab>
    </Tabs>
  )
}

export default DocumentContent
