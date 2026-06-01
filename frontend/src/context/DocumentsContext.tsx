import { createContext, useContext, useMemo, useState } from 'react'
import { DocumentDetail } from '../services/api'

interface DocumentsState {
  openDocs: DocumentDetail[]
  activeDocId: string | null
  openDocument: (doc: DocumentDetail) => void
  closeDocument: (id: string) => void
  setActiveDocId: (id: string) => void
}

const DocumentsContext = createContext<DocumentsState | null>(null)

export function DocumentsProvider({ children }: { children: React.ReactNode }) {
  const [openDocs, setOpenDocs] = useState<DocumentDetail[]>([])
  const [activeDocId, setActiveDocId] = useState<string | null>(null)

  const value = useMemo<DocumentsState>(() => ({
    openDocs,
    activeDocId,
    openDocument: (doc) => {
      setOpenDocs((prev) => {
        const existingIndex = prev.findIndex((d) => d.id === doc.id)
        if (existingIndex === -1) return [...prev, doc]
        const next = [...prev]
        next[existingIndex] = doc
        return next
      })
      setActiveDocId(doc.id)
    },
    closeDocument: (id) => {
      setOpenDocs((prev) => prev.filter((d) => d.id !== id))
      setActiveDocId((curr) => (curr === id ? null : curr))
    },
    setActiveDocId
  }), [openDocs, activeDocId])

  return <DocumentsContext.Provider value={value}>{children}</DocumentsContext.Provider>
}

export function useDocumentsContext() {
  const ctx = useContext(DocumentsContext)
  if (!ctx) throw new Error('DocumentsContext missing')
  return ctx
}
