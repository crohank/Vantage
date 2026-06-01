import { ArrowUpRight, FileText, Newspaper, Upload as UploadIcon } from 'lucide-react'
import ScenarioCard from './ScenarioCard'
import MemoViewer from './MemoViewer'
import StockStats from './StockStats'
import { Card, CardHeader, CardContent } from './ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Progress } from './ui/progress'
import { Separator } from './ui/separator'
import { AnalysisResults, DocumentRecord } from '../services/api'
import { cn, formatNumber } from '../lib/utils'

interface ResultsDisplayProps {
  results: AnalysisResults
  onViewDocument?: (documentId: string) => void
  selectedDocumentId?: string
}

function recTone(rec: string): 'bull' | 'bear' | 'neutral' {
  const r = rec.toLowerCase()
  if (r.includes('buy')) return 'bull'
  if (r.includes('sell')) return 'bear'
  return 'neutral'
}

function sourceIcon(type: string) {
  if (type === 'sec_filing') return <FileText size={14} className="text-primary" />
  if (type === 'news_article') return <Newspaper size={14} className="text-warning" />
  return <UploadIcon size={14} className="text-muted-foreground" />
}

function sourceLabel(type: string) {
  if (type === 'sec_filing') return 'SEC'
  if (type === 'news_article') return 'News'
  return 'Upload'
}

function ResultsDisplay({ results, onViewDocument, selectedDocumentId }: ResultsDisplayProps) {
  const recommendation = results?.recommendation || 'N/A'
  const confidence = results?.confidence_score || 0
  const scenarios = results?.scenarios || {}
  const memo = results?.memo || ''
  const documentSources = results?.document_sources || []
  const tone = recTone(recommendation)

  const scenarioOrder = ['bull', 'base', 'bear']
  const orderedScenarios = Object.entries(scenarios).sort(
    ([a], [b]) => scenarioOrder.indexOf(a.toLowerCase()) - scenarioOrder.indexOf(b.toLowerCase())
  )

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Hero recommendation */}
      <Card
        className={cn(
          'overflow-hidden border-l-4',
          tone === 'bull' && 'border-l-bull',
          tone === 'bear' && 'border-l-bear',
          tone === 'neutral' && 'border-l-warning'
        )}
      >
        <CardContent className="grid grid-cols-1 gap-6 p-6 md:grid-cols-[1fr_auto]">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Recommendation
              </span>
            </div>
            <div className="flex items-baseline gap-4">
              <span
                className={cn(
                  'font-mono text-5xl font-bold uppercase tracking-tight tabular-nums',
                  tone === 'bull' && 'text-bull',
                  tone === 'bear' && 'text-bear',
                  tone === 'neutral' && 'text-warning'
                )}
              >
                {recommendation}
              </span>
              <Badge variant={tone === 'bull' ? 'bull' : tone === 'bear' ? 'bear' : 'warning'}>
                {tone === 'bull' ? 'Long bias' : tone === 'bear' ? 'Short bias' : 'Hold'}
              </Badge>
            </div>
          </div>

          <div className="flex w-full flex-col gap-2 md:w-64">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Confidence
              </span>
              <span className="font-mono text-2xl font-bold tabular-nums text-foreground">
                {(confidence * 100).toFixed(0)}
                <span className="text-[14px] text-muted-foreground">%</span>
              </span>
            </div>
            <Progress
              value={confidence * 100}
              indicatorClassName={cn(
                tone === 'bull' && 'bg-bull',
                tone === 'bear' && 'bg-bear',
                tone === 'neutral' && 'bg-warning'
              )}
            />
          </div>
        </CardContent>
      </Card>

      {/* Stock stats */}
      <StockStats marketData={results?.market_data} />

      {/* Tabbed detail */}
      <Card>
        <Tabs defaultValue="scenarios" className="w-full">
          <CardHeader className="flex-row items-center justify-between border-b border-border pb-3">
            <TabsList>
              <TabsTrigger value="scenarios">Scenarios</TabsTrigger>
              {memo && <TabsTrigger value="memo">Memo</TabsTrigger>}
              {documentSources.length > 0 && (
                <TabsTrigger value="sources">Sources · {documentSources.length}</TabsTrigger>
              )}
              {results?.telemetry?.num_calls ? <TabsTrigger value="telemetry">Telemetry</TabsTrigger> : null}
              {results?.timing && <TabsTrigger value="timing">Timing</TabsTrigger>}
            </TabsList>
          </CardHeader>

          <CardContent className="p-4">
            <TabsContent value="scenarios" className="mt-0">
              {orderedScenarios.length > 0 ? (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  {orderedScenarios.map(([name, data]) => (
                    <ScenarioCard
                      key={name}
                      name={name}
                      returnValue={data.return || 0}
                      probability={data.prob || 0}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState message="No scenarios available" />
              )}
            </TabsContent>

            {memo && (
              <TabsContent value="memo" className="mt-0">
                <MemoViewer memo={memo} />
              </TabsContent>
            )}

            {documentSources.length > 0 && (
              <TabsContent value="sources" className="mt-0">
                <ul className="space-y-1.5">
                  {documentSources.map((doc) => (
                    <SourceRow
                      key={doc.id || `${doc.source_type}-${doc.title}`}
                      doc={doc}
                      active={!!doc.id && doc.id === selectedDocumentId}
                      onOpen={onViewDocument}
                    />
                  ))}
                </ul>
              </TabsContent>
            )}

            {results?.telemetry?.num_calls ? (
              <TabsContent value="telemetry" className="mt-0">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  <TelemetryStat label="LLM Calls" value={formatNumber(results.telemetry.num_calls)} />
                  <TelemetryStat
                    label="Total Tokens"
                    value={(results.telemetry.total_tokens || 0).toLocaleString()}
                  />
                  <TelemetryStat
                    label="Prompt Tokens"
                    value={(results.telemetry.prompt_tokens || 0).toLocaleString()}
                  />
                  <TelemetryStat
                    label="Completion"
                    value={(results.telemetry.completion_tokens || 0).toLocaleString()}
                  />
                  <TelemetryStat
                    label="Latency"
                    value={`${((results.telemetry.total_latency_ms || 0) / 1000).toFixed(1)}s`}
                  />
                  <TelemetryStat
                    label="Est. Cost"
                    value={`$${(results.telemetry.total_cost_usd || 0).toFixed(4)}`}
                  />
                </div>
              </TabsContent>
            ) : null}

            {results?.timing && (
              <TabsContent value="timing" className="mt-0">
                <ul className="divide-y divide-border rounded-md border border-border">
                  {Object.entries(results.timing).map(([step, duration]) => (
                    <li key={step} className="flex items-center justify-between px-3 py-2 text-[13px]">
                      <span className="text-foreground">{step}</span>
                      <span className="font-mono tabular-nums text-primary">
                        {duration >= 60
                          ? `${Math.floor(duration / 60)}m ${(duration % 60).toFixed(1)}s`
                          : `${duration.toFixed(1)}s`}
                      </span>
                    </li>
                  ))}
                </ul>
              </TabsContent>
            )}
          </CardContent>
        </Tabs>
      </Card>
    </div>
  )
}

interface SourceRowProps {
  doc: DocumentRecord
  active: boolean
  onOpen?: (id: string) => void
}

function SourceRow({ doc, active, onOpen }: SourceRowProps) {
  const meta = [
    sourceLabel(doc.source_type),
    doc.ticker,
    doc.filing_date && `Filed ${doc.filing_date}`,
    doc.published_at && new Date(doc.published_at).toLocaleDateString()
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <li
      className={cn(
        'group flex items-center gap-3 rounded-md border bg-surface px-3 py-2 transition-colors',
        active ? 'border-primary/50 bg-primary/5' : 'border-border hover:border-border-strong'
      )}
    >
      <div className="shrink-0">{sourceIcon(doc.source_type)}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-foreground">
          {doc.title || doc.filename || 'Untitled document'}
        </div>
        <div className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {meta}
        </div>
      </div>
      {onOpen && doc.id && (
        <Button
          variant={active ? 'default' : 'outline'}
          size="sm"
          onClick={() => onOpen(doc.id)}
          className="shrink-0"
        >
          {active ? 'Viewing' : 'Open'}
          {!active && <ArrowUpRight size={12} />}
        </Button>
      )}
    </li>
  )
}

function TelemetryStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-[16px] font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-surface-elevated/30 px-4 py-10 text-center">
      <p className="text-[12px] text-muted-foreground">{message}</p>
    </div>
  )
}

// Re-export Separator so tree-shaker keeps it (used elsewhere)
export { Separator }
export default ResultsDisplay
