import { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Form, Row } from 'react-bootstrap'
import { useNavigate, useParams } from 'react-router-dom'
import HorizonSelect from '../components/HorizonSelect'
import ProgressDisplay from '../components/ProgressDisplay'
import RecentAnalyses from '../components/RecentAnalyses'
import ResultsDisplay from '../components/ResultsDisplay'
import RiskProfileSelect from '../components/RiskProfileSelect'
import TickerInput from '../components/TickerInput'
import { analyzeStockWithProgress, fetchAnalysisById, fetchDocumentById, isLikelyTicker, resolveQuery, AnalysisResults, ProgressData } from '../services/api'
import { useDocumentsContext } from '../context/DocumentsContext'

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

  useEffect(() => {
    if (!analysisId) return
    fetchAnalysisById(analysisId).then((analysis) => {
      setResults({
        recommendation: analysis.recommendation,
        confidence_score: analysis.confidenceScore,
        scenarios: analysis.scenarios || {},
        memo: analysis.memoMarkdown || '',
        market_data: analysis.marketData || {},
        macro_data: analysis.macroData || {},
        risk_analysis: analysis.riskAnalysis || {},
        document_sources: analysis.documentsUsed || []
      })
      setTicker(analysis.ticker || '')
      setHorizon((analysis.horizon || 'medium') as Horizon)
      setRiskProfile((analysis.riskProfile || 'moderate') as RiskProfile)
    }).catch(() => undefined)
  }, [analysisId])

  const handleAnalyze = async () => {
    if (!ticker.trim()) return
    setIsAnalyzing(true); setProgress([]); setError(null); setResults(null); setResolvedTicker(null)
    let actualTicker = ticker.trim().toUpperCase()
    if (!isLikelyTicker(ticker.trim())) {
      setIsResolving(true)
      const resolution = await resolveQuery(ticker.trim())
      setIsResolving(false)
      if (!resolution.ticker) { setError('Unable to resolve ticker'); setIsAnalyzing(false); return }
      actualTicker = resolution.ticker; setResolvedTicker(actualTicker)
    }
    const controller = analyzeStockWithProgress(actualTicker, horizon, riskProfile, uploadedFile, (p) => setProgress((prev) => [...prev, p]), (data) => {
      setIsAnalyzing(false)
      setResults(data.data || null)
      setAbortController(null)
    }, (err) => { setError(err.message); setIsAnalyzing(false); setAbortController(null) })
    setAbortController(controller)
  }

  const handleOpenDocument = async (documentId: string) => {
    const doc = await fetchDocumentById(documentId)
    openDocument(doc)
    navigate(`/documents/${documentId}`)
  }

  return (
    <Row className="g-4">
      <Col xl={2} lg={3}>
        <Card className="theme-card sticky-rail">
          <Card.Body>
            <h6 className="mb-3">Recent</h6>
            <RecentAnalyses />
          </Card.Body>
        </Card>
      </Col>
      <Col xl={10} lg={9}>
        <Card className="theme-card mb-4">
          <Card.Body>
            <TickerInput value={ticker} onChange={(v) => { setTicker(v); setResolvedTicker(null) }} resolvedTicker={resolvedTicker} isResolving={isResolving} />
            <HorizonSelect value={horizon} onChange={setHorizon} />
            <RiskProfileSelect value={riskProfile} onChange={setRiskProfile} />
            <Form.Group className="mb-3">
              <Form.Label>Upload PDF</Form.Label>
              <Form.Control type="file" accept=".pdf,application/pdf" onChange={(e) => setUploadedFile(e.target.files?.[0] || null)} />
            </Form.Group>
            <Button className="w-100" onClick={handleAnalyze} disabled={isAnalyzing || !ticker.trim()}>{isAnalyzing ? 'Analyzing...' : 'Run Analysis'}</Button>
            {isAnalyzing && abortController && <Button variant="danger" className="w-100 mt-2" onClick={() => abortController.abort()}>Cancel</Button>}
            {error && <Alert variant="danger" className="mt-3">{error}</Alert>}
          </Card.Body>
        </Card>
        {results && <ResultsDisplay results={results} onViewDocument={handleOpenDocument} />}
        {isAnalyzing && <ProgressDisplay progress={progress} />}
      </Col>
    </Row>
  )
}

export default AnalysePage
