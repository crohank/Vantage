import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import report from '../api/eval-report.json'
import { cn } from '../lib/utils'

/**
 * What the diff engine actually scores.
 *
 * The numbers are the committed output of `run_diff_eval --json`, which is
 * the same run that gates CI. Nothing here is typed by hand, so the page
 * cannot drift from the gate without the file changing.
 */
function MetricsPage() {
  const perType = Object.entries(report.classification.per_type).map(([type, v]) => ({
    type,
    recall: v.total ? v.correct / v.total : 0,
    correct: v.correct,
    total: v.total,
  }))

  const generated = new Date(report.generated_at)
  const citationsPerfect = report.citations.validity === 1

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header>
        <h1 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
          Diff engine scores
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Ground truth is generated, not labelled. A real filing section is taken, a known set
          of edits is applied, and the resulting edit script is the expected output. That is
          what makes recall measurable at all: hand-labelling one 70,000 character Item 1A is
          a day of work.
        </p>
        <p className="mt-2 font-mono text-[11px] text-muted-foreground">
          {report.cases} cases, generated {generated.toISOString().slice(0, 16).replace('T', ' ')}
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-4">
        <Metric label="Precision" value={report.detection.precision} />
        <Metric label="Recall" value={report.detection.recall} />
        <Metric label="F1" value={report.detection.f1} />
        <Metric
          label="Citation validity"
          value={report.citations.validity}
          tone={citationsPerfect ? 'bull' : 'bear'}
          note={`${report.citations.valid} of ${report.citations.checked}`}
        />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
          Recall by change type
        </h2>
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={perType} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <XAxis
                dataKey="type"
                stroke="hsl(var(--muted-foreground))"
                tick={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={[0, 1]}
                stroke="hsl(var(--muted-foreground))"
                tick={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <Tooltip
                cursor={{ fill: 'hsl(var(--muted))', opacity: 0.3 }}
                contentStyle={{
                  background: 'hsl(var(--popover))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 6,
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 11,
                }}
                formatter={(_value, _name, item) => {
                  const row = (item as { payload?: (typeof perType)[number] }).payload
                  return row ? [`${row.correct} / ${row.total}`, 'correct'] : []
                }}
              />
              <Bar dataKey="recall" radius={[3, 3, 0, 0]}>
                {perType.map((row) => (
                  <Cell
                    key={row.type}
                    // Moved is the weakest type and the misses land in
                    // added, so it is worth singling out rather than
                    // averaging away.
                    fill={row.recall >= 0.95 ? 'hsl(var(--bull))' : 'hsl(var(--warning))'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
          Confusion matrix
        </h2>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          Rows expected, columns reported. A single accuracy figure hides which direction the
          errors run.
        </p>
        <ConfusionTable matrix={report.classification.matrix} />
      </section>

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
          Citation validity is a gate, not a score
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Every emitted span must slice out of the stored section text byte for byte. A finding
          that fails is discarded rather than down-ranked, at runtime and in CI. The threshold
          is {report.citations.validity === 1 ? '1.0' : 'below 1.0'}, so any drift fails the
          build.
        </p>
      </section>
    </div>
  )
}

function Metric({
  label,
  value,
  tone = 'default',
  note,
}: {
  label: string
  value: number
  tone?: 'default' | 'bull' | 'bear'
  note?: string
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          'mt-1 font-mono text-2xl tabular-nums',
          tone === 'bull' && 'text-bull',
          tone === 'bear' && 'text-bear'
        )}
      >
        {(value * 100).toFixed(1)}%
      </div>
      {note && <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{note}</div>}
    </div>
  )
}

function ConfusionTable({
  matrix,
}: {
  matrix: { expected: string; reported: string; count: number }[]
}) {
  const types = [...new Set(matrix.flatMap((m) => [m.expected, m.reported]))].sort()
  const at = (expected: string, reported: string) =>
    matrix.find((m) => m.expected === expected && m.reported === reported)?.count ?? 0

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full font-mono text-xs tabular-nums">
        <thead>
          <tr className="text-muted-foreground">
            <th className="py-1 pr-4 text-left font-normal" />
            {types.map((t) => (
              <th key={t} className="px-2 py-1 text-right font-normal">
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {types.map((expected) => (
            <tr key={expected} className="border-t border-border">
              <td className="py-1 pr-4 text-muted-foreground">{expected}</td>
              {types.map((reported) => {
                const n = at(expected, reported)
                const correct = expected === reported
                return (
                  <td
                    key={reported}
                    className={cn(
                      'px-2 py-1 text-right',
                      n === 0 && 'text-muted-foreground/40',
                      n > 0 && correct && 'text-bull',
                      n > 0 && !correct && 'text-warning'
                    )}
                  >
                    {n}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default MetricsPage
