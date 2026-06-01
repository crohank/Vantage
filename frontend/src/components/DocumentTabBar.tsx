import { X, FileText, Newspaper, Upload } from 'lucide-react'
import { useDocumentsContext } from '../context/DocumentsContext'
import { cn } from '../lib/utils'

function iconFor(type: string) {
  if (type === 'sec_filing') return FileText
  if (type === 'news_article') return Newspaper
  return Upload
}

function DocumentTabBar() {
  const { openDocs, activeDocId, setActiveDocId, closeDocument } = useDocumentsContext()
  if (openDocs.length === 0) return null

  return (
    <div className="flex items-center gap-0.5 overflow-x-auto border-b border-border bg-surface-elevated/40 px-2 pt-1.5">
      {openDocs.map((doc) => {
        const Icon = iconFor(doc.source_type)
        const active = doc.id === activeDocId
        const label = doc.title || doc.filename || doc.source_name || doc.id
        return (
          <div
            key={doc.id}
            className={cn(
              'group flex max-w-[220px] items-center gap-1.5 rounded-t-md border border-b-0 px-2.5 py-1.5 text-[12px] transition-colors',
              active
                ? 'border-border bg-background text-foreground'
                : 'border-transparent text-muted-foreground hover:bg-surface hover:text-foreground'
            )}
          >
            <button
              type="button"
              onClick={() => setActiveDocId(doc.id)}
              className="flex min-w-0 items-center gap-1.5"
            >
              <Icon size={12} className="shrink-0" />
              <span className="truncate">{label}</span>
            </button>
            <button
              type="button"
              onClick={() => closeDocument(doc.id)}
              className="shrink-0 rounded p-0.5 text-muted-foreground opacity-60 transition-opacity hover:bg-surface hover:text-foreground group-hover:opacity-100"
              aria-label="Close tab"
            >
              <X size={11} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

export default DocumentTabBar
