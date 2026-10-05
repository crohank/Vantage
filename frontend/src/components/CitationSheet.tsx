import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Check } from 'lucide-react'
import { getSection, type Finding, type Section } from '../api/client'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet'
import { Skeleton } from './ui/skeleton'

// Characters of surrounding filing text to show either side of the span.
// Enough to read the sentence in context without loading a whole Item 1A
// into the DOM.
const CONTEXT_CHARS = 1200

interface CitationSheetProps {
  jobId: string | null
  finding: Finding | null
  onClose: () => void
}

/**
 * Opens the source filing at the cited span.
 *
 * This is the interaction that makes groundedness checkable rather than a
 * number in a table: the span is re-sliced out of the section text the
 * engine actually diffed, and the result says whether it matched.
 */
function CitationSheet({ jobId, finding, onClose }: CitationSheetProps) {
  const [section, setSection] = useState<Section | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const highlightRef = useRef<HTMLSpanElement>(null)

  const span = finding?.current_span ?? finding?.prior_span ?? null

  useEffect(() => {
    if (!jobId || !span) return
    let cancelled = false

    setLoading(true)
    setError(null)
    setSection(null)

    getSection(jobId, span.accession, span.section_id)
      .then((s) => {
        if (!cancelled) setSection(s)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load the filing')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [jobId, span])

  useEffect(() => {
    if (section && highlightRef.current) {
      highlightRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [section])

  const open = Boolean(finding && span)

  // Re-slice the span out of the stored text. The backend already refuses to
  // emit a finding whose span does not resolve, so a mismatch here means the
  // two sides disagree, which is worth showing rather than hiding.
  const quoted = section && span ? section.text.slice(span.start, span.end) : null
  const verified = quoted !== null && span !== null && quoted === span.quote

  const before =
    section && span ? section.text.slice(Math.max(0, span.start - CONTEXT_CHARS), span.start) : ''
  const after = section && span ? section.text.slice(span.end, span.end + CONTEXT_CHARS) : ''

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 sm:max-w-2xl">
        <SheetHeader className="border-b border-border pb-4">
          <SheetTitle className="font-mono text-sm">
            {section?.heading ?? 'Loading filing'}
          </SheetTitle>
          {span && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
              <span>{span.accession}</span>
              <span>
                chars {span.start.toLocaleString()} to {span.end.toLocaleString()}
              </span>
              {section && <span>of {section.char_length.toLocaleString()}</span>}
            </div>
          )}
          {section && (
            <div
              className={cnVerified(verified)}
              role="status"
            >
              {verified ? <Check size={12} /> : <AlertCircle size={12} />}
              {verified
                ? 'Quote matches the filing text exactly'
                : 'Quote does not match the filing text'}
            </div>
          )}
        </SheetHeader>

        <div className="flex-1 overflow-y-auto py-4">
          {loading && (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-10/12" />
            </div>
          )}

          {error && (
            <p className="flex items-center gap-2 font-mono text-xs text-destructive">
              <AlertCircle size={14} />
              {error}
            </p>
          )}

          {section && span && (
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
              {before}
              <span
                ref={highlightRef}
                className="rounded bg-warning/20 px-0.5 font-medium text-foreground ring-1 ring-warning/40"
              >
                {quoted}
              </span>
              {after}
            </p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function cnVerified(verified: boolean): string {
  const base =
    'mt-2 inline-flex w-fit items-center gap-1.5 rounded px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.1em]'
  return verified ? `${base} bg-bull/10 text-bull` : `${base} bg-destructive/10 text-destructive`
}

export default CitationSheet
