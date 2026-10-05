import { Activity, AlertTriangle } from 'lucide-react'
import type { Attention } from '../api/client'
import { cn } from '../lib/utils'

const SOURCE_LABELS: Record<string, string> = {
  hackernews: 'Hacker News',
  bluesky: 'Bluesky',
  reddit: 'Reddit',
  news: 'News',
}

/**
 * Public discussion volume, normalised against the ticker's own baseline.
 *
 * Deliberately labelled as discussion rather than as market pricing. An
 * absolute mention count means nothing without knowing whether this ticker
 * normally draws three mentions or three thousand, so the z-score is what
 * carries the signal.
 */
function AttentionPanel({ attention }: { attention: Attention }) {
  const live = attention.signals.filter((s) => s.available)

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
        <Activity size={12} />
        Attention, past {attention.window_days} days
      </h2>

      <div className="mt-3 flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <div>
          <span className="font-mono text-2xl tabular-nums">
            {(attention.score * 100).toFixed(0)}
          </span>
          <span className="ml-1 font-mono text-xs text-muted-foreground">/ 100</span>
        </div>
        <div className="font-mono text-xs text-muted-foreground">
          {attention.total_mentions.toLocaleString()} mentions across {live.length} source
          {live.length === 1 ? '' : 's'}
        </div>
      </div>

      {attention.is_degraded && (
        <p className="mt-2 flex items-center gap-1.5 font-mono text-[11px] text-warning">
          <AlertTriangle size={12} />
          Some sources were unavailable, so this understates attention
        </p>
      )}

      <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
        {attention.signals.map((s) => (
          <li key={s.source} className="flex items-center gap-3 font-mono text-[11px]">
            <span className="w-24 shrink-0 text-muted-foreground">
              {SOURCE_LABELS[s.source] ?? s.source}
            </span>
            {s.available ? (
              <>
                <span className="w-16 tabular-nums">{s.mention_count.toLocaleString()}</span>
                <span
                  className={cn(
                    'tabular-nums',
                    s.z_score > 1 && 'text-bull',
                    s.z_score < -1 && 'text-bear',
                    Math.abs(s.z_score) <= 1 && 'text-muted-foreground'
                  )}
                >
                  {s.z_score >= 0 ? '+' : ''}
                  {s.z_score.toFixed(2)} sigma
                </span>
              </>
            ) : (
              <span className="text-muted-foreground">{s.error ?? 'not configured'}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default AttentionPanel
