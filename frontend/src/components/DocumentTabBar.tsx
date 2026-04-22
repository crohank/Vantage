import { Button } from 'react-bootstrap'
import { useDocumentsContext } from '../context/DocumentsContext'

function DocumentTabBar() {
  const { openDocs, activeDocId, setActiveDocId, closeDocument } = useDocumentsContext()
  return (
    <div className="d-flex gap-2 flex-wrap mb-2">
      {openDocs.map((doc) => (
        <div key={doc.id} className={`px-2 py-1 rounded ${doc.id === activeDocId ? 'bg-primary-subtle' : 'bg-dark'}`}>
          <Button size="sm" variant="link" onClick={() => setActiveDocId(doc.id)}>{doc.title || doc.filename || doc.id}</Button>
          <Button size="sm" variant="link" onClick={() => closeDocument(doc.id)}>x</Button>
        </div>
      ))}
    </div>
  )
}

export default DocumentTabBar
