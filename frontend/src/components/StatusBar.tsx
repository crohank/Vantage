import { useDocumentsContext } from '../context/DocumentsContext'

function StatusBar() {
  const { openDocs, activeDocId } = useDocumentsContext()
  const doc = openDocs.find((d) => d.id === activeDocId)

  return (
    <div className="flex items-center justify-between gap-3 border-t border-border bg-surface-elevated/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
      {doc ? (
        <>
          <span className="flex items-center gap-3">
            <span>
              <span className="text-muted-foreground/70">TKR </span>
              <span className="text-foreground">{doc.ticker || '—'}</span>
            </span>
            <span>
              <span className="text-muted-foreground/70">TYPE </span>
              <span className="text-foreground">{doc.source_type || '—'}</span>
            </span>
            {doc.filing_date && (
              <span>
                <span className="text-muted-foreground/70">FILED </span>
                <span className="text-foreground">{doc.filing_date}</span>
              </span>
            )}
            {doc.chunks != null && (
              <span>
                <span className="text-muted-foreground/70">CHUNKS </span>
                <span className="text-foreground">{doc.chunks}</span>
              </span>
            )}
          </span>
          <span className="text-muted-foreground/70">ID {doc.id.slice(0, 8)}</span>
        </>
      ) : (
        <span>No document selected</span>
      )}
    </div>
  )
}

export default StatusBar
