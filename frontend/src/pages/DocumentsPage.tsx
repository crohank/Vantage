import { useEffect, useState } from 'react'
import { Button, Card, Col, Row } from 'react-bootstrap'
import { useNavigate, useParams } from 'react-router-dom'
import DocumentContent from '../components/DocumentContent'
import DocumentTabBar from '../components/DocumentTabBar'
import DocumentTree from '../components/DocumentTree'
import StatusBar from '../components/StatusBar'
import { fetchDocumentById, fetchDocuments, DocumentRecord } from '../services/api'
import { useDocumentsContext } from '../context/DocumentsContext'

function DocumentsPage() {
  const { documentId } = useParams()
  const navigate = useNavigate()
  const { openDocument } = useDocumentsContext()
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchDocuments({ limit: 200 }).then(setDocuments).catch(() => undefined)
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
    <Row className="g-3">
      <Col xl={3}>
        <Card className="theme-card" style={{ resize: 'horizontal', overflow: 'auto', minWidth: 240 }}>
          <Card.Body>
            <DocumentTree documents={documents} search={search} setSearch={setSearch} onOpen={onOpen} />
            <Button className="w-100 mt-3" size="sm" disabled>+ Upload PDF</Button>
          </Card.Body>
        </Card>
      </Col>
      <Col xl={9}>
        <Card className="theme-card">
          <Card.Body>
            <DocumentTabBar />
            <DocumentContent />
            <StatusBar />
          </Card.Body>
        </Card>
      </Col>
    </Row>
  )
}

export default DocumentsPage
