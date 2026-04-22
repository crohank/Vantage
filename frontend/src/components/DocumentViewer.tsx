import { Card, Tabs, Tab, Button, Alert, Badge } from 'react-bootstrap'
import { DocumentDetail, resolveDocumentUrl } from '../services/api'

interface DocumentViewerProps {
  document: DocumentDetail | null
  loading?: boolean
  error?: string | null
  isVisible?: boolean
}

function DocumentViewer({ document, loading = false, error, isVisible = true }: DocumentViewerProps) {
  if (!isVisible) {
    return null
  }

  const title = document?.title || document?.filename || 'Document Viewer'
  const pdfUrl = resolveDocumentUrl(document?.file_url) || resolveDocumentUrl(document?.source_url)
  const hasText = Boolean(document?.preview_text && document.preview_text.trim())

  return (
    <aside className="viewer-shell" data-bs-theme="dark">
      <Card className="theme-card viewer-panel">
        <Card.Header className="d-flex justify-content-between align-items-center">
          <div>
            <h3 className="mb-1">Document Viewer</h3>
            <small className="app-subtle">Persistent side preview panel</small>
          </div>
          {document?.source_type && (
            <Badge bg={document.source_type === 'sec_filing' ? 'primary' : 'secondary'}>
              {document.source_type === 'sec_filing' ? 'SEC' : 'Upload'}
            </Badge>
          )}
        </Card.Header>
        <Card.Body>
          {loading && <div className="text-muted">Loading document preview...</div>}
          {error && <Alert variant="danger">{error}</Alert>}

          {!loading && !error && !document && (
            <div className="viewer-empty">
              <div>
                <div className="fw-semibold mb-2">Select a document</div>
                <small>Pick a document from the analysis lists to preview it here.</small>
              </div>
            </div>
          )}

          {!loading && !error && document && (
            <>
              <div className="mb-3">
                <div className="fw-semibold">{title}</div>
                <small className="app-subtle">
                  {document.ticker || 'N/A'}
                  {document.filing_date ? ` | Filed: ${document.filing_date}` : ''}
                </small>
              </div>
              <Tabs defaultActiveKey={hasText ? 'text' : 'pdf'} id="document-viewer-tabs" className="mb-3">
                <Tab eventKey="pdf" title="PDF">
                  {pdfUrl ? (
                    <div>
                      <div className="d-flex justify-content-end mb-2">
                        <Button size="sm" variant="outline-primary" href={pdfUrl} target="_blank" rel="noreferrer">
                          Open in New Tab
                        </Button>
                      </div>
                      <iframe
                        src={pdfUrl}
                        title={title}
                        style={{ width: '100%', height: '56vh', border: '1px solid #2b354d', borderRadius: '8px' }}
                      />
                    </div>
                  ) : (
                    <Alert variant="warning" className="mb-0">
                      PDF preview is not available for this document.
                    </Alert>
                  )}
                </Tab>
                <Tab eventKey="text" title="Text Preview">
                  {hasText ? (
                    <div
                      className="document-text-preview"
                      style={{
                        maxHeight: '56vh',
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap',
                        border: '1px solid #2b354d',
                        borderRadius: '8px',
                        padding: '1rem',
                        background: '#121a2b'
                      }}
                    >
                      {document.preview_text}
                    </div>
                  ) : (
                    <Alert variant="warning" className="mb-0">
                      No extracted text preview is available for this document yet.
                    </Alert>
                  )}
                </Tab>
                <Tab eventKey="meta" title="Metadata">
                  <div className="small">
                    <div><strong>ID:</strong> {document.id}</div>
                    <div><strong>Source Type:</strong> {document.source_type || 'N/A'}</div>
                    <div><strong>Filename:</strong> {document.filename || 'N/A'}</div>
                    <div><strong>Chunks:</strong> {document.chunks ?? 'N/A'}</div>
                    <div><strong>Updated:</strong> {document.updated_at ? new Date(document.updated_at).toLocaleString() : 'N/A'}</div>
                  </div>
                </Tab>
              </Tabs>
            </>
          )}
        </Card.Body>
      </Card>
    </aside>
  )
}

export default DocumentViewer
