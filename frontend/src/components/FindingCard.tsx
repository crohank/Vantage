import { FileDiff, Minus, MoveRight, Pencil, Plus, Sparkles, Users } from 'lucide-react'
import type { Finding } from '../api/client'
import { cn } from '../lib/utils'

const CHANGE_META = {
  added: { icon: Plus, label: 'Added', tone: 'bull' },
  removed: { icon: Minus, label: 'Removed', tone: 'bear' },
  reworded: { icon: Pencil, label: 'Reworded', tone: 'neutral' },
  moved: { icon: MoveRight, label: 'Moved', tone: 'neutral' },
} as const

const KIND_META = {
  diff: { icon: FileDiff, label: 'Change' },
  novelty: { icon: Sparkles, label: 'First use' },
  peer: { icon: Users, label: 'Sector-wide' },
} as const

const SECTION_LABELS: Record<string, string> = {
  item_1_business: 'Business',
  item_1a_risk_factors: 'Risk Factors',
  item_1c_cybersecurity: 'Cybersecurity',
  item_3_legal_proceedings: 'Legal Proceedings',
  item_7_mda: 'MD&A',
  item_9a_controls: 'Controls',
}

interface FindingCardProps {
  finding: Finding
  onOpenCitation: (finding: Finding) => void
}

function FindingCard({ finding, onOpenCitation }: FindingCardProps) {
  const change = finding.change_type ? CHANGE_META[finding.change_type] : null
  const kind = KIND_META[finding.kind]
  const KindIcon = kind.icon
  const ChangeIcon = change?.icon
  const band = finding.materiality.band
  const score = finding.materiality.score

  // A reworded paragraph is the one case where both sides carry text, so it
  // is the only one worth rendering as a before and after pair.
  const showsBothSides = finding.change_type === 'reworded' && finding.prior_span

  return (
    <article
      className={cn(
        'rounded-lg border bg-card p-4 transition-colors',
        band === 'high' && 'border-warning/40',
        band !== 'high' && 'border-border'
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
          <KindIcon size={12} />
          {kind.label}
        </span>

        {change && ChangeIcon && (
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.1em]',
              change.tone === 'bull' && 'bg-bull/10 text-bull',
              change.tone === 'bear' && 'bg-bear/10 text-bear',
              change.tone === 'neutral' && 'bg-muted text-muted-foreground'
            )}
          >
            <ChangeIcon size={10} />
            {change.label}
          </span>
        )}

        <span className="font-mono text-[11px] text-muted-foreground">
          {SECTION_LABELS[finding.section_id] ?? finding.section_id}
        </span>

        <span className="ml-auto flex items-center gap-2">
          <span
            className={cn(
              'font-mono text-[10px] font-bold uppercase tracking-[0.1em]',
              band === 'high' && 'text-warning',
              band === 'medium' && 'text-foreground',
              band === 'low' && 'text-muted-foreground'
            )}
          >
            {band}
          </span>
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            {score.toFixed(2)}
          </span>
        </span>
      </header>

      {finding.summary && (
        <p className="mt-3 text-sm leading-relaxed text-foreground">{finding.summary}</p>
      )}

      {showsBothSides && finding.prior_span && (
        <blockquote className="mt-3 border-l-2 border-bear/40 pl-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            Before
          </span>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            {finding.prior_span.quote}
          </p>
        </blockquote>
      )}

      {finding.current_span && (
        <blockquote
          className={cn(
            'mt-3 border-l-2 pl-3',
            showsBothSides ? 'border-bull/40' : 'border-border-strong'
          )}
        >
          {showsBothSides && (
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              After
            </span>
          )}
          <p className="mt-1 text-sm leading-relaxed text-foreground">
            {finding.current_span.quote}
          </p>
        </blockquote>
      )}

      {!finding.current_span && finding.prior_span && !showsBothSides && (
        <blockquote className="mt-3 border-l-2 border-bear/40 pl-3">
          <p className="text-sm leading-relaxed text-muted-foreground line-through decoration-bear/40">
            {finding.prior_span.quote}
          </p>
        </blockquote>
      )}

      {finding.novelty_phrase && (
        <p className="mt-3 font-mono text-[11px] text-muted-foreground">
          Phrase <span className="text-foreground">&ldquo;{finding.novelty_phrase}&rdquo;</span>
          {finding.novelty_first_seen
            ? ` first used ${finding.novelty_first_seen}`
            : ' not used before'}
        </p>
      )}

      {finding.peer_total != null && (
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          {finding.peer_ciks.length} of {finding.peer_total} sector filings used the same language
        </p>
      )}

      <footer className="mt-3 flex items-center justify-between border-t border-border pt-3">
        <span className="font-mono text-[10px] text-muted-foreground">
          {finding.current_accession ?? finding.prior_accession}
        </span>
        {/* Every finding resolves to a verbatim span, so this is always
            available. A finding that could not quote its source is dropped
            before it reaches the client. */}
        <button
          type="button"
          onClick={() => onOpenCitation(finding)}
          className="font-mono text-[11px] text-primary underline-offset-4 hover:underline"
        >
          View in filing
        </button>
      </footer>
    </article>
  )
}

export default FindingCard
