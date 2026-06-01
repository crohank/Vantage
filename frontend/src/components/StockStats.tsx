import { cn, formatCurrency, formatLargeNumber, formatNumber, formatPercent } from '../lib/utils'

interface StockStatsProps {
  marketData?: {
    valuation?: {
      current_price?: number
      '52_week_high'?: number
      '52_week_low'?: number
      pe_ratio?: number
      forward_pe?: number
      market_cap?: number
      dividend_yield?: number
      pb_ratio?: number
      ps_ratio?: number
    }
  }
}

function Stat({
  label,
  value,
  accent = false,
  mono = true
}: {
  label: string
  value: React.ReactNode
  accent?: boolean
  mono?: boolean
}) {
  return (
    <div className="flex flex-col gap-0.5 border-l border-border px-3 py-1 first:border-l-0 first:pl-0">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          mono && 'font-mono tabular-nums',
          accent ? 'text-[20px] font-bold text-foreground' : 'text-[14px] font-semibold text-foreground'
        )}
      >
        {value}
      </span>
    </div>
  )
}

function StockStats({ marketData }: StockStatsProps) {
  if (!marketData?.valuation) return null
  const v = marketData.valuation

  const rangePos =
    v['52_week_high'] && v['52_week_low'] && v.current_price && v['52_week_high'] !== v['52_week_low']
      ? (v.current_price - v['52_week_low']) / (v['52_week_high'] - v['52_week_low'])
      : null

  const divYield = v.dividend_yield != null ? v.dividend_yield * 100 : null

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      {/* Hero row: price + market cap + 52w range */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[auto_1fr_auto]">
        <Stat label="Current Price" value={formatCurrency(v.current_price)} accent />

        <div className="flex flex-col gap-1 px-3 sm:border-l sm:border-border">
          <div className="flex items-center justify-between text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            <span>52W Range</span>
            {rangePos !== null && (
              <span className="font-mono normal-case tracking-normal">
                {rangePos > 0.7 ? 'Near high' : rangePos < 0.3 ? 'Near low' : 'Mid range'}
              </span>
            )}
          </div>
          <div className="relative mt-1 h-1.5 w-full rounded-full bg-surface-elevated">
            <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-bear via-warning to-bull"
              style={{ width: '100%', opacity: 0.4 }}
            />
            {rangePos !== null && (
              <div
                className="absolute top-1/2 h-3 w-1 -translate-y-1/2 -translate-x-1/2 rounded-full bg-foreground shadow"
                style={{ left: `${Math.max(0, Math.min(1, rangePos)) * 100}%` }}
              />
            )}
          </div>
          <div className="flex justify-between font-mono text-[11px] tabular-nums text-muted-foreground">
            <span>{formatCurrency(v['52_week_low'])}</span>
            <span>{formatCurrency(v['52_week_high'])}</span>
          </div>
        </div>

        <Stat label="Market Cap" value={formatLargeNumber(v.market_cap)} accent />
      </div>

      {/* Ratios row */}
      <div className="grid grid-cols-2 gap-2 border-t border-border pt-3 sm:grid-cols-5">
        <Stat label="P/E" value={formatNumber(v.pe_ratio)} />
        <Stat label="Fwd P/E" value={formatNumber(v.forward_pe)} />
        <Stat label="P/B" value={formatNumber(v.pb_ratio)} />
        <Stat label="P/S" value={formatNumber(v.ps_ratio)} />
        <Stat
          label="Div Yield"
          value={
            divYield !== null && divYield > 0 ? (
              <span className="text-bull">{formatPercent(divYield)}</span>
            ) : (
              '—'
            )
          }
        />
      </div>
    </div>
  )
}

export default StockStats
