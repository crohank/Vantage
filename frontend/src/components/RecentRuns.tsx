import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listAnalyses, type JobSummary } from '../api/client'
import { Skeleton } from './ui/skeleton'
import { cn } from '../lib/utils'

function RecentRuns({ activeJobId }: { activeJobId: string | null }) {
  const [runs, setRuns] = useState<JobSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Refetch when the active run changes so a finished run appears here
  // without a reload.
  useEffect(() => {
    let cancelled = false
    listAnalyses(12)
      .then((r) => !cancelled && setRuns(r))
      .catch((e: unknown) =>
        !cancelled && setError(e instanceof Error ? e.message : 'Could not load recent runs')
      )
    return () => {
      cancelled = true
    }
  }, [activeJobId])

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
        Recent
      </h2>

      {error && <p className="mt-3 font-mono text-[11px] text-destructive">{error}</p>}

      {!runs && !error && (
        <div className="mt-3 space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      )}

      {runs?.length === 0 && (
        <p className="mt-3 font-mono text-[11px] text-muted-foreground">No runs yet.</p>
      )}

      <ul className="mt-3 space-y-1">
        {runs?.map((run) => (
          <li key={run.job_id}>
            <Link
              to={`/findings/${run.job_id}`}
              className={cn(
                'flex items-center justify-between gap-2 rounded px-2 py-1.5 font-mono text-xs hover:bg-muted',
                run.job_id === activeJobId && 'bg-muted'
              )}
            >
              <span className="font-bold">{run.ticker}</span>
              <span
                className={cn(
                  'text-[10px] uppercase tracking-[0.1em]',
                  run.status === 'succeeded' && 'text-bull',
                  run.status === 'failed' && 'text-bear',
                  run.status === 'running' && 'text-warning',
                  !['succeeded', 'failed', 'running'].includes(run.status) &&
                    'text-muted-foreground'
                )}
              >
                {run.status === 'succeeded' ? `${run.finding_count}` : run.status}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default RecentRuns
