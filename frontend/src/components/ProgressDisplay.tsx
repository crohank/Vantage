import { useEffect, useRef } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from './ui/card'
import { ProgressData } from '../services/api'
import { cn } from '../lib/utils'

interface ProgressDisplayProps {
  progress: ProgressData[]
}

function statusTone(step: string): 'error' | 'success' | 'info' | 'muted' {
  const s = step.toLowerCase()
  if (s.includes('error')) return 'error'
  if (s.includes('ok') || s.includes('complete')) return 'success'
  if (
    s.includes('market') ||
    s.includes('macro') ||
    s.includes('risk') ||
    s.includes('scenario') ||
    s.includes('memo') ||
    s.includes('news')
  )
    return 'info'
  return 'muted'
}

function ProgressDisplay({ progress }: ProgressDisplayProps) {
  const endRef = useRef<HTMLLIElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [progress])

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between border-b border-border pb-3">
        <CardTitle className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
          </span>
          Analysis Stream
        </CardTitle>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {progress.length} events
        </span>
      </CardHeader>
      <CardContent className="p-0">
        <div className="max-h-[360px] overflow-y-auto bg-surface-elevated/30 px-4 py-3 font-mono text-[12px]">
          {progress.length === 0 ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <span className="animate-pulse">▍</span>
              <span>Initializing agents…</span>
            </div>
          ) : (
            <ol className="space-y-1.5">
              {progress.map((item, i) => {
                const tone = statusTone(item.step)
                const ts = new Date(item.timestamp).toLocaleTimeString(undefined, {
                  hour12: false,
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit'
                })
                return (
                  <li key={i} className="flex items-start gap-3 leading-relaxed">
                    <span className="shrink-0 text-muted-foreground/70">{ts}</span>
                    <span
                      className={cn(
                        'mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full',
                        tone === 'error' && 'bg-bear',
                        tone === 'success' && 'bg-bull',
                        tone === 'info' && 'bg-primary',
                        tone === 'muted' && 'bg-muted-foreground/40'
                      )}
                    />
                    <span className="min-w-0 flex-1 break-words text-foreground/90">{item.message}</span>
                  </li>
                )
              })}
              <li ref={endRef} />
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default ProgressDisplay
