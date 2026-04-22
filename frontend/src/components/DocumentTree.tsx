import { Form, ListGroup } from 'react-bootstrap'
import { DocumentRecord } from '../services/api'

function DocumentTree({ documents, search, setSearch, onOpen }: { documents: DocumentRecord[]; search: string; setSearch: (v: string) => void; onOpen: (id: string) => void }) {
  const filtered = documents.filter((d) => `${d.ticker} ${d.title || d.filename || ''}`.toLowerCase().includes(search.toLowerCase()))
  return (
    <div>
      <Form.Control value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search documents" className="mb-2" />
      <div className="text-muted small mb-2">SEC Filings</div>
      <ListGroup className="mb-3">
        {filtered.filter((d) => d.source_type === 'sec_filing').map((d) => <ListGroup.Item key={d.id} action onClick={() => onOpen(d.id)}>{d.ticker} - {d.title || '10-K'}</ListGroup.Item>)}
      </ListGroup>
      <div className="text-muted small mb-2">Uploaded PDFs</div>
      <ListGroup>
        {filtered.filter((d) => d.source_type !== 'sec_filing').map((d) => <ListGroup.Item key={d.id} action onClick={() => onOpen(d.id)}>{d.filename || d.title || d.id}</ListGroup.Item>)}
      </ListGroup>
    </div>
  )
}

export default DocumentTree
