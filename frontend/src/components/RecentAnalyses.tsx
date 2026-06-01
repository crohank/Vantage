import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { History } from 'lucide-react'
import { fetchAnalyses, AnalysisRecord } from '../services/api'
import { Skeleton } from './ui/skeleton'
import { cn } from '../lib/utils'

function recommendationTone(rec: string): 'bull' | 'bear' | 'neutral' {
  const r = rec.toLowerCase()
  if (r.includes('buy')) return 'bull'
  if (r.includes('sell')) return 'bear'
  return 'neutral'
}

function RecentAnalyses() {
  const [items, setItems] = useState<AnalysisRecord[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const { analysisId } = useParams()

  useEffect(() => {
    fetchAnalyses({ limit: 12 })
      .then(setItems)
      .catch(() => undefined)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center">
        <History className="text-muted-foreground" size={20} />
        <p className="text-[12px] text-muted-foreground">No analyses yet.<br />Run your first one →</p>
      </div>
    )
  }

  return (
    <ul className="space-y-1">
      {items.map((item) => {
        const tone = recommendationTone(item.recommendation || '')
        const isActive = item._id === analysisId
        return (
          <li key={item._id}>
            <button
              type="button"
              onClick={() => navigate(`/analyse/${item._id}`)}
              className={cn(
                'group w-full rounded-md border px-2.5 py-2 text-left transition-colors',
                isActive
                  ? 'border-primary/40 bg-primary/5'
                  : 'border-transparent hover:border-border hover:bg-surface'
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[13px] font-semibold tracking-wide text-foreground">
                  {item.ticker}
                </span>
                <span
                  className={cn(
                    'rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider',
                    tone === 'bull' && 'bg-bull/15 text-bull',
                    tone === 'bear' && 'bg-bear/15 text-bear',
                    tone === 'neutral' && 'bg-surface-elevated text-muted-foreground'
                  )}
                >
                  {item.recommendation || '—'}
                </span>
              </div>
              <div className="mt-0.5 flex items-center justify-between text-[11px] text-muted-foreground">
                <span className="capitalize">{item.horizon || 'medium'}</span>
                <span className="font-mono">
                  {item.createdAt
                    ? new Date(item.createdAt).toLocaleDateString(undefined, {
                        month: 'short',
                        day: 'numeric'
                      })
                    : ''}
                </span>
              </div>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export default RecentAnalyses
