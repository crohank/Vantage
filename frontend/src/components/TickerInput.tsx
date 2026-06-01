import { useEffect, useRef } from 'react'
import { Loader2, CheckCircle2 } from 'lucide-react'
import { Input } from './ui/input'
import { Label } from './ui/label'

interface TickerInputProps {
  value: string
  onChange: (value: string) => void
  resolvedTicker?: string | null
  isResolving?: boolean
}

function TickerInput({ value, onChange, resolvedTicker, isResolving }: TickerInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== '/') return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return
      e.preventDefault()
      inputRef.current?.focus()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target.value
    const isTickerLike = /^[A-Za-z0-9-]*$/.test(input) && !input.includes(' ')
    onChange(isTickerLike ? input.toUpperCase() : input)
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor="ticker">Ticker or Question</Label>
      <div className="relative">
        <Input
          ref={inputRef}
          id="ticker"
          type="text"
          value={value}
          onChange={handleChange}
          placeholder="AAPL  /  How is Apple doing?"
          maxLength={200}
          className="font-mono text-[14px] tracking-wide h-10 pr-24"
          autoComplete="off"
          spellCheck={false}
        />
        {!value && !isResolving && (
          <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-border bg-surface-elevated px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            /
          </kbd>
        )}
        {(isResolving || resolvedTicker) && (
          <div className="absolute inset-y-0 right-2 flex items-center gap-1 text-[11px]">
            {isResolving ? (
              <span className="flex items-center gap-1 text-muted-foreground">
                <Loader2 size={11} className="animate-spin" />
                Resolving…
              </span>
            ) : (
              <span className="flex items-center gap-1 rounded bg-bull/15 px-1.5 py-0.5 font-mono font-semibold text-bull">
                <CheckCircle2 size={11} />
                {resolvedTicker}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default TickerInput
