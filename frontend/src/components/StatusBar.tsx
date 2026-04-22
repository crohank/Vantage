import { useDocumentsContext } from '../context/DocumentsContext'

function StatusBar() {
  const { openDocs, activeDocId } = useDocumentsContext()
  const doc = openDocs.find((d) => d.id === activeDocId)
  return (
    <div className="small text-muted border-top pt-2 mt-2">
      {doc ? `${doc.ticker || 'N/A'} | ${doc.source_type || 'N/A'} | Filed: ${doc.filing_date || 'N/A'}` : 'No document selected'}
    </div>
  )
}

export default StatusBar
