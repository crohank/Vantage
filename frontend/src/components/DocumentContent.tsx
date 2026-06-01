import { FileX } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs'
import { resolveDocumentUrl } from '../services/api'
import { useDocumentsContext } from '../context/DocumentsContext'

function DocumentContent() {
  const { openDocs, activeDocId } = useDocumentsContext()
  const doc = openDocs.find((d) => d.id === activeDocId) || null

  if (!doc) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border bg-surface-elevated/30 py-20 text-center">
        <FileX className="text-muted-foreground" size={28} />
        <div>
          <p className="text-[13px] font-medium text-foreground">No document selected</p>
          <p className="text-[12px] text-muted-foreground">Choose a document from the tree to inspect it.</p>
        </div>
      </div>
    )
  }

  const pdfUrl = resolveDocumentUrl(doc.file_url)
  const sourceUrl = resolveDocumentUrl(doc.source_url)
  const defaultTab = doc.has_pdf ? 'pdf' : doc.has_text_preview ? 'text' : doc.has_source_url ? 'source' : 'meta'

  return (
    <Tabs key={doc.id} defaultValue={defaultTab} className="flex h-full flex-col">
      <TabsList>
        {doc.has_pdf && <TabsTrigger value="pdf">PDF</TabsTrigger>}
        {doc.has_source_url && <TabsTrigger value="source">Source</TabsTrigger>}
        <TabsTrigger value="text">Text</TabsTrigger>
        <TabsTrigger value="meta">Metadata</TabsTrigger>
      </TabsList>

      {doc.has_pdf && (
        <TabsContent value="pdf" className="flex-1">
          <div className="overflow-hidden rounded-md border border-border bg-surface">
            <iframe
              src={pdfUrl || ''}
              title={doc.id}
              className="block h-[70vh] w-full border-0"
            />
          </div>
        </TabsContent>
      )}

      {doc.has_source_url && (
        <TabsContent value="source" className="flex-1">
          <div className="overflow-hidden rounded-md border border-border bg-surface">
            <iframe
              src={sourceUrl || ''}
              title={`${doc.id}-source`}
              className="block h-[70vh] w-full border-0"
            />
          </div>
        </TabsContent>
      )}

      <TabsContent value="text" className="flex-1">
        <div className="max-h-[70vh] overflow-auto rounded-md border border-border bg-surface-elevated/30 p-4 font-mono text-[12px] leading-relaxed text-foreground/90 whitespace-pre-wrap">
          {doc.preview_text || (
            <span className="text-muted-foreground">No extracted text available for this document.</span>
          )}
        </div>
      </TabsContent>

      <TabsContent value="meta" className="flex-1">
        <pre className="max-h-[70vh] overflow-auto rounded-md border border-border bg-surface-elevated/30 p-4 font-mono text-[11px] leading-relaxed text-foreground/90">
          {JSON.stringify(doc, null, 2)}
        </pre>
      </TabsContent>
    </Tabs>
  )
}

export default DocumentContent
