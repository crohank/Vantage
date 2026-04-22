import { Card, Form, ListGroup, Badge, Button } from 'react-bootstrap'
import { DocumentRecord } from '../services/api'

interface DocumentsCatalogProps {
  documents: DocumentRecord[]
  tickerFilter: string
  onTickerFilterChange: (value: string) => void
  onViewDocument?: (documentId: string) => void
  selectedDocumentId?: string
}

function DocumentsCatalog({ documents, tickerFilter, onTickerFilterChange, onViewDocument, selectedDocumentId }: DocumentsCatalogProps) {
  return (
    <Card className="theme-card mb-4 shadow">
      <Card.Header className="d-flex justify-content-between align-items-center">
        <h2 className="mb-0">Documents Analyzed</h2>
        <Form.Control
          value={tickerFilter}
          onChange={(e) => onTickerFilterChange(e.target.value)}
          placeholder="Filter by ticker"
          style={{ maxWidth: '180px' }}
        />
      </Card.Header>
      <Card.Body>
        {documents.length === 0 ? (
          <div className="text-muted">No documents have been registered yet.</div>
        ) : (
          <ListGroup>
            {documents.map((doc) => (
              <ListGroup.Item key={doc.id} className={doc.id && doc.id === selectedDocumentId ? 'doc-row-selected' : ''}>
                <div className="d-flex justify-content-between align-items-center">
                  <div>
                    <div className="fw-semibold">{doc.title || doc.filename || 'Untitled document'}</div>
                    <small className="text-muted">
                      {doc.ticker} | {doc.source_type === 'sec_filing' ? 'SEC Pulled' : 'Uploaded PDF'}
                      {doc.filing_date ? ` | Filed: ${doc.filing_date}` : ''}
                      {doc.updated_at ? ` | Updated: ${new Date(doc.updated_at).toLocaleString()}` : ''}
                    </small>
                  </div>
                  <Badge bg={doc.source_type === 'sec_filing' ? 'primary' : 'secondary'}>
                    {doc.source_type === 'sec_filing' ? 'SEC' : 'Upload'}
                  </Badge>
                </div>
                {onViewDocument && doc.id && (
                  <div className="mt-2">
                    <Button
                      size="sm"
                      variant={doc.id === selectedDocumentId ? 'primary' : 'outline-primary'}
                      onClick={() => onViewDocument(doc.id)}
                    >
                      {doc.id === selectedDocumentId ? 'Viewing' : 'View in Side Panel'}
                    </Button>
                  </div>
                )}
              </ListGroup.Item>
            ))}
          </ListGroup>
        )}
      </Card.Body>
    </Card>
  )
}

export default DocumentsCatalog
