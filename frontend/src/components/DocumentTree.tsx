import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, FileText, Newspaper, Search, Upload } from 'lucide-react'
import { Input } from './ui/input'
import { DocumentRecord } from '../services/api'
import { cn } from '../lib/utils'

interface DocumentTreeProps {
  documents: DocumentRecord[]
  search: string
  setSearch: (v: string) => void
  onOpen: (id: string) => void
  activeId?: string | null
}

const GROUPS: { key: string; label: string; match: (d: DocumentRecord) => boolean; icon: typeof FileText }[] = [
  { key: 'sec', label: 'SEC Filings', match: (d) => d.source_type === 'sec_filing', icon: FileText },
  { key: 'news', label: 'News Articles', match: (d) => d.source_type === 'news_article', icon: Newspaper },
  {
    key: 'pdf',
    label: 'Uploaded PDFs',
    match: (d) => d.source_type !== 'sec_filing' && d.source_type !== 'news_article',
    icon: Upload
  }
]

function DocumentTree({ documents, search, setSearch, onOpen, activeId }: DocumentTreeProps) {
  const filtered = useMemo(() => {
    if (!search.trim()) return documents
    const q = search.toLowerCase()
    return documents.filter(
      (d) =>
        `${d.ticker} ${d.title || ''} ${d.filename || ''} ${d.source_name || ''}`.toLowerCase().includes(q)
    )
  }, [documents, search])

  const grouped = useMemo(
    () => GROUPS.map((g) => ({ ...g, items: filtered.filter(g.match) })),
    [filtered]
  )

  return (
    <div className="flex h-full flex-col">
      <div className="relative px-3 pt-3">
        <Search
          size={13}
          className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search documents…"
          className="h-8 pl-7 text-[12px]"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3">
        {grouped.map((group) => (
          <DocumentGroup
            key={group.key}
            label={group.label}
            icon={group.icon}
            items={group.items}
            onOpen={onOpen}
            activeId={activeId}
          />
        ))}
        {filtered.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Search className="text-muted-foreground" size={20} />
            <p className="text-[12px] text-muted-foreground">No documents match your search.</p>
          </div>
        )}
      </div>
    </div>
  )
}

interface GroupProps {
  label: string
  icon: typeof FileText
  items: DocumentRecord[]
  onOpen: (id: string) => void
  activeId?: string | null
}

function DocumentGroup({ label, icon: Icon, items, onOpen, activeId }: GroupProps) {
  const [open, setOpen] = useState(true)
  if (items.length === 0) return null
  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 rounded-sm px-1 py-1 text-left text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Icon size={12} />
        <span>{label}</span>
        <span className="ml-auto font-mono normal-case tracking-normal text-muted-foreground/70">
          {items.length}
        </span>
      </button>
      {open && (
        <ul className="mt-0.5 space-y-0.5">
          {items.map((d) => {
            const active = d.id === activeId
            const title = d.title || d.filename || d.source_name || d.id
            const sub = [d.ticker, d.filing_date].filter(Boolean).join(' · ')
            return (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => onOpen(d.id)}
                  className={cn(
                    'group flex w-full flex-col items-start gap-0 rounded-md px-2 py-1.5 text-left transition-colors',
                    active
                      ? 'bg-primary/10 text-foreground'
                      : 'text-foreground/85 hover:bg-surface hover:text-foreground'
                  )}
                >
                  <span className="line-clamp-1 w-full text-[12px] font-medium">{title}</span>
                  {sub && (
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                      {sub}
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export default DocumentTree
