import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, FileUp, Play, Square, X } from 'lucide-react'
import HorizonSelect from '../components/HorizonSelect'
import ProgressDisplay from '../components/ProgressDisplay'
import RecentAnalyses from '../components/RecentAnalyses'
import ResultsDisplay from '../components/ResultsDisplay'
import RiskProfileSelect from '../components/RiskProfileSelect'
import TickerInput from '../components/TickerInput'
import { Button } from '../components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card'
import { Label } from '../components/ui/label'
import { Separator } from '../components/ui/separator'
import {
  analyzeStockWithProgress,
  fetchAnalysisById,
  fetchDocumentById,
  isLikelyTicker,
  resolveQuery,
  AnalysisResults,
  ProgressData
} from '../services/api'
import { useDocumentsContext } from '../context/DocumentsContext'
import { cn } from '../lib/utils'

type Horizon = 'short' | 'medium' | 'long'
type RiskProfile = 'conservative' | 'moderate' | 'aggressive'

function AnalysePage() {
  const navigate = useNavigate()
  const { analysisId } = useParams()
  const { openDocument } = useDocumentsContext()
  const [ticker, setTicker] = useState('')
  const [horizon, setHorizon] = useState<Horizon>('medium')
  const [riskProfile, setRiskProfile] = useState<RiskProfile>('moderate')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [progress, setProgress] = useState<ProgressData[]>([])
  const [results, setResults] = useState<AnalysisResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [abortController, setAbortController] = useState<{ abort: () => void } | null>(null)
  const [resolvedTicker, setResolvedTicker] = useState<string | null>(null)
  const [isResolving, setIsResolving] = useState(false)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [dragActive, setDragActive] = useState(false)

  useEffect(() => {
    if (!analysisId) return
    fetchAnalysisById(analysisId)
      .then((analysis) => {
        setResults({
          recommendation: analysis.recommendation,
          confidence_score: analysis.confidenceScore,
          scenarios: analysis.scenarios || {},
          memo: analysis.memoMarkdown || '',
          market_data: analysis.marketData || {},
          macro_data: analysis.macroData || {},
          news_analysis: analysis.newsAnalysis || {},
          risk_analysis: analysis.riskAnalysis || {},
          document_sources: analysis.documentsUsed || []
        })
        setTicker(analysis.ticker || '')
        setHorizon((analysis.horizon || 'medium') as Horizon)
        setRiskProfile((analysis.riskProfile || 'moderate') as RiskProfile)
      })
      .catch(() => undefined)
  }, [analysisId])

  const handleAnalyze = async () => {
    if (!ticker.trim()) return
    setIsAnalyzing(true)
    setProgress([])
    setError(null)
    setResults(null)
    setResolvedTicker(null)
    let actualTicker = ticker.trim().toUpperCase()
    if (!isLikelyTicker(ticker.trim())) {
      setIsResolving(true)
      const resolution = await resolveQuery(ticker.trim())
      setIsResolving(false)
      if (!resolution.ticker) {
        setError('Unable to resolve ticker from query')
        setIsAnalyzing(false)
        return
      }
      actualTicker = resolution.ticker
      setResolvedTicker(actualTicker)
    }
    const controller = analyzeStockWithProgress(
      actualTicker,
      horizon,
      riskProfile,
      uploadedFile,
      (p) => setProgress((prev) => [...prev, p]),
      (data) => {
        setIsAnalyzing(false)
        setResults(data.data || null)
        setAbortController(null)
      },
      (err) => {
        setError(err.message)
        setIsAnalyzing(false)
        setAbortController(null)
      }
    )
    setAbortController(controller)
  }

  const handleOpenDocument = async (documentId: string) => {
    const doc = await fetchDocumentById(documentId)
    openDocument(doc)
    navigate(`/documents/${documentId}`)
  }

  const handleFileSelect = (file: File | null) => {
    if (!file) return setUploadedFile(null)
    if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
      setUploadedFile(file)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
      {/* Left rail */}
      <aside className="lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)] lg:overflow-auto">
        <Card>
          <CardHeader className="border-b border-border pb-3">
            <CardTitle>Recent</CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <RecentAnalyses />
          </CardContent>
        </Card>
      </aside>

      {/* Main column */}
      <div className="space-y-4">
        {/* Command panel */}
        <Card>
          <CardHeader className="flex-row items-center justify-between border-b border-border pb-3">
            <CardTitle>Command Panel</CardTitle>
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              new analysis
            </span>
          </CardHeader>
          <CardContent className="space-y-4 p-4">
            <TickerInput
              value={ticker}
              onChange={(v) => {
                setTicker(v)
                setResolvedTicker(null)
              }}
              resolvedTicker={resolvedTicker}
              isResolving={isResolving}
            />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <HorizonSelect value={horizon} onChange={setHorizon} />
              <RiskProfileSelect value={riskProfile} onChange={setRiskProfile} />
            </div>

            <Separator />

            {/* PDF dropzone */}
            <div className="space-y-1.5">
              <Label>Additional Document (optional)</Label>
              <label
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragActive(true)
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragActive(false)
                  handleFileSelect(e.dataTransfer.files?.[0] || null)
                }}
                className={cn(
                  'flex cursor-pointer items-center justify-between gap-3 rounded-md border border-dashed border-border bg-surface-elevated/40 px-3 py-2.5 transition-colors hover:border-border-strong',
                  dragActive && 'border-primary bg-primary/5'
                )}
              >
                <div className="flex items-center gap-2.5">
                  <FileUp size={16} className="text-muted-foreground" />
                  <div className="flex flex-col">
                    {uploadedFile ? (
                      <>
                        <span className="font-mono text-[12px] text-foreground">
                          {uploadedFile.name}
                        </span>
                        <span className="text-[11px] text-muted-foreground">
                          {(uploadedFile.size / 1024).toFixed(1)} KB · PDF
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="text-[12px] text-foreground">Drop PDF or click to browse</span>
                        <span className="text-[11px] text-muted-foreground">
                          Earnings, transcript, research report…
                        </span>
                      </>
                    )}
                  </div>
                </div>
                {uploadedFile && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault()
                      setUploadedFile(null)
                    }}
                    className="rounded p-1 text-muted-foreground hover:bg-surface hover:text-foreground"
                  >
                    <X size={14} />
                  </button>
                )}
                <input
                  type="file"
                  accept=".pdf,application/pdf"
                  className="hidden"
                  onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                />
              </label>
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-md border border-bear/30 bg-bear/10 px-3 py-2 text-[12px] text-bear">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <Button
                onClick={handleAnalyze}
                disabled={isAnalyzing || !ticker.trim()}
                className="flex-1"
                size="lg"
              >
                {isAnalyzing ? (
                  <>
                    <span className="h-2 w-2 animate-pulse rounded-full bg-primary-foreground/70" />
                    Analyzing…
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    Run Analysis
                  </>
                )}
              </Button>
              {isAnalyzing && abortController && (
                <Button
                  variant="destructive"
                  size="lg"
                  onClick={() => abortController.abort()}
                >
                  <Square size={12} />
                  Cancel
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {isAnalyzing && <ProgressDisplay progress={progress} />}
        {results && <ResultsDisplay results={results} onViewDocument={handleOpenDocument} />}
      </div>
    </div>
  )
}

export default AnalysePage
