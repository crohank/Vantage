import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, Loader2, Search, X } from 'lucide-react'
import {
  ApiError,
  NODE_LABELS,
  cancelAnalysis,
  getAnalysis,
  streamAnalysis,
  submitAnalysis,
  type AnalysisResult,
  type Finding,
  type RequestKind,
} from '../api/client'
import FindingCard from '../components/FindingCard'
import CitationSheet from '../components/CitationSheet'
import AttentionPanel from '../components/AttentionPanel'
import RecentRuns from '../components/RecentRuns'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '../components/ui/toggle-group'
import { Skeleton } from '../components/ui/skeleton'
import { cn } from '../lib/utils'

const KINDS: { value: RequestKind; label: string; hint: string }[] = [
  { value: 'diff', label: 'Diff', hint: 'Changed language only' },
  { value: 'full', label: 'Full', hint: 'Diff, first use, peers, attention' },
]

type Phase = 'idle' | 'running' | 'done' | 'error'

function FindingsPage() {
  const { jobId: routeJobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()

  const [ticker, setTicker] = useState('')
  const [kind, setKind] = useState<RequestKind>('diff')
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState<string[]>([])
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [citation, setCitation] = useState<Finding | null>(null)
  const [activeJob, setActiveJob] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // "/" focuses the ticker box, as in the terminals this borrows from.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement !== inputRef.current) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Rehydrate a run from its URL, so a finding can be linked to directly.
  useEffect(() => {
    if (!routeJobId || routeJobId === activeJob) return
    setPhase('running')
    setActiveJob(routeJobId)
    getAnalysis(routeJobId)
      .then((r) => {
        setResult(r)
        setTicker(r.ticker)
        setPhase(r.status === 'succeeded' ? 'done' : 'error')
        if (r.status !== 'succeeded') setError(`Run ${r.status}`)
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.message : 'Could not load that run')
        setPhase('error')
      })
  }, [routeJobId, activeJob])

  const run = useCallback(async () => {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setPhase('running')
    setProgress([])
    setResult(null)
    setError(null)

    try {
      const job = await submitAnalysis({ ticker: symbol, kind })
      setActiveJob(job.job_id)
      navigate(`/findings/${job.job_id}`, { replace: true })

      const streamed = await streamAnalysis(
        job.job_id,
        (event) => {
          if (event.type === 'node_start') {
            setProgress((p) => [...p, NODE_LABELS[event.node] ?? event.node])
          } else if (event.type === 'error') {
            setError(event.message)
          }
        },
        controller.signal,
      )

      // The stream carries the result, but fall back to a fetch so a dropped
      // connection still lands on a finished run rather than an empty page.
      const final = streamed ?? (await getAnalysis(job.job_id))
      setResult(final)
      setPhase(final.status === 'succeeded' ? 'done' : 'error')
      if (final.status !== 'succeeded') {
        setError(final.errors[0] ?? `Run ${final.status}`)
      }
    } catch (e: unknown) {
      if (controller.signal.aborted) {
        setPhase('idle')
        return
      }
      setError(e instanceof Error ? e.message : 'Something went wrong')
      setPhase('error')
    }
  }, [ticker, kind, navigate])

  const stop = useCallback(async () => {
    abortRef.current?.abort()
    if (activeJob) await cancelAnalysis(activeJob).catch(() => undefined)
    setPhase('idle')
  }, [activeJob])

  const findings = result?.findings ?? []

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="order-2 lg:order-1">
        <RecentRuns activeJobId={activeJob} />
      </aside>

      <main className="order-1 min-w-0 space-y-6 lg:order-2">
        <section className="rounded-lg border border-border bg-card p-4">
          <h1 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
            Compare filings
          </h1>

          <form
            className="mt-3 flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              void run()
            }}
          >
            <div className="min-w-[180px] flex-1">
              <label
                htmlFor="ticker"
                className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground"
              >
                Ticker
              </label>
              <Input
                id="ticker"
                ref={inputRef}
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="AAPL"
                maxLength={8}
                autoComplete="off"
                className="mt-1 font-mono uppercase"
              />
            </div>

            <div>
              <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                Depth
              </span>
              <ToggleGroup
                type="single"
                value={kind}
                onValueChange={(v) => v && setKind(v as RequestKind)}
                className="mt-1 justify-start"
              >
                {KINDS.map((k) => (
                  <ToggleGroupItem key={k.value} value={k.value} title={k.hint}>
                    {k.label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>

            {phase === 'running' ? (
              <Button type="button" variant="secondary" onClick={() => void stop()}>
                <X size={14} className="mr-1.5" />
                Cancel
              </Button>
            ) : (
              <Button type="submit" disabled={!ticker.trim()}>
                <Search size={14} className="mr-1.5" />
                Run
              </Button>
            )}
          </form>

          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            Compares the two most recent annual filings and reports what changed, each quote
            resolvable to its exact position in the source document.
          </p>
        </section>

        {phase === 'running' && (
          <section className="rounded-lg border border-border bg-card p-4">
            <h2 className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
              <Loader2 size={12} className="animate-spin" />
              Running
            </h2>
            <ol className="mt-3 space-y-1">
              {progress.map((step, i) => (
                <li
                  key={`${step}-${i}`}
                  className="font-mono text-xs text-muted-foreground"
                >
                  <span className="text-bull">ok</span> {step}
                </li>
              ))}
              {progress.length === 0 && (
                <li className="font-mono text-xs text-muted-foreground">Starting</li>
              )}
            </ol>
          </section>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
            <AlertCircle size={16} className="mt-0.5 shrink-0 text-destructive" />
            <p className="font-mono text-xs text-destructive">{error}</p>
          </div>
        )}

        {phase === 'running' && !result && (
          <div className="space-y-3">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        )}

        {result && result.status === 'succeeded' && (
          <>
            <section className="rounded-lg border border-border bg-card p-4">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="font-mono text-2xl font-bold tracking-tight">{result.ticker}</h2>
                <span className="text-sm text-muted-foreground">{result.company_name}</span>
                {result.prior_filing && result.current_filing && (
                  <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
                    {result.prior_filing.fiscal_label} to {result.current_filing.fiscal_label}
                  </span>
                )}
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Stat label="Findings" value={findings.length.toString()} />
                <Stat
                  label="High materiality"
                  value={findings.filter((f) => f.materiality.band === 'high').length.toString()}
                />
                <Stat
                  label="Sections"
                  value={new Set(findings.map((f) => f.section_id)).size.toString()}
                />
                <Stat
                  label="Elapsed"
                  value={`${result.timings.reduce((a, t) => a + t.seconds, 0).toFixed(1)}s`}
                />
              </dl>

              {/* Partial failures are shown rather than hidden behind a
                  plausible-looking result. */}
              {result.errors.length > 0 && (
                <ul className="mt-4 space-y-1 border-t border-border pt-3">
                  {result.errors.map((e) => (
                    <li key={e} className="font-mono text-[11px] text-warning">
                      {e}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {result.attention && <AttentionPanel attention={result.attention} />}

            <section className="space-y-3">
              <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
                Findings, most material first
              </h2>
              {findings.length === 0 ? (
                <p className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground">
                  Nothing changed materially between these two filings.
                </p>
              ) : (
                findings.map((f) => (
                  <FindingCard key={f.id} finding={f} onOpenCitation={setCitation} />
                ))
              )}
            </section>
          </>
        )}

        {phase === 'idle' && !result && (
          <p className={cn('rounded-lg border border-dashed border-border p-10 text-center')}>
            <span className="font-mono text-sm text-muted-foreground">
              Enter a ticker to compare its two most recent annual filings.
            </span>
          </p>
        )}
      </main>

      <CitationSheet jobId={activeJob} finding={citation} onClose={() => setCitation(null)} />
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-0.5 font-mono text-lg tabular-nums">{value}</dd>
    </div>
  )
}

export default FindingsPage
