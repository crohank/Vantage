import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { cn, formatPercent } from '../lib/utils'

interface ScenarioCardProps {
  name: string
  returnValue: number
  probability: number
}

function ScenarioCard({ name, returnValue, probability }: ScenarioCardProps) {
  const returnPct = returnValue * 100
  const probPct = probability * 100
  const isPositive = returnValue >= 0
  const lower = name.toLowerCase()
  const tone: 'bull' | 'bear' | 'neutral' =
    lower === 'bull' ? 'bull' : lower === 'bear' ? 'bear' : 'neutral'

  const Icon = tone === 'bull' ? TrendingUp : tone === 'bear' ? TrendingDown : Minus

  return (
    <div
      className={cn(
        'flex h-full flex-col gap-3 rounded-lg border bg-card p-4',
        tone === 'bull' && 'border-bull/30',
        tone === 'bear' && 'border-bear/30',
        tone === 'neutral' && 'border-border'
      )}
    >
      <div className="flex items-center justify-between">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.15em]',
            tone === 'bull' && 'text-bull',
            tone === 'bear' && 'text-bear',
            tone === 'neutral' && 'text-muted-foreground'
          )}
        >
          <Icon size={12} />
          {name}
        </span>
      </div>

      <div className="flex items-baseline gap-2">
        <span
          className={cn(
            'font-mono text-3xl font-bold tabular-nums tracking-tight',
            isPositive ? 'text-bull' : 'text-bear'
          )}
        >
          {formatPercent(returnPct, 1)}
        </span>
      </div>

      <div className="mt-auto space-y-1.5">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-muted-foreground">Probability</span>
          <span className="font-mono font-semibold text-foreground">{probPct.toFixed(0)}%</span>
        </div>
        <div className="h-1 w-full overflow-hidden rounded-full bg-surface-elevated">
          <div
            className={cn(
              'h-full transition-all',
              tone === 'bull' && 'bg-bull',
              tone === 'bear' && 'bg-bear',
              tone === 'neutral' && 'bg-muted-foreground'
            )}
            style={{ width: `${probPct}%` }}
          />
        </div>
      </div>
    </div>
  )
}

export default ScenarioCard
