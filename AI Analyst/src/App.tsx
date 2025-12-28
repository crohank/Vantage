import { useState } from 'react'
import { Container, Row, Col, Card, Button, Alert } from 'react-bootstrap'
import TickerInput from './components/TickerInput'
import HorizonSelect from './components/HorizonSelect'
import RiskProfileSelect from './components/RiskProfileSelect'
import ProgressDisplay from './components/ProgressDisplay'
import ResultsDisplay from './components/ResultsDisplay'
import { analyzeStockWithProgress, ProgressData, AnalysisResults } from './services/api'

type Horizon = 'short' | 'medium' | 'long'
type RiskProfile = 'conservative' | 'moderate' | 'aggressive'

function App() {
  const [ticker, setTicker] = useState<string>('')
  const [horizon, setHorizon] = useState<Horizon>('medium')
  const [riskProfile, setRiskProfile] = useState<RiskProfile>('moderate')
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false)
  const [progress, setProgress] = useState<ProgressData[]>([])
  const [results, setResults] = useState<AnalysisResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [abortController, setAbortController] = useState<{ abort: () => void } | null>(null)

  const handleAnalyze = () => {
    if (!ticker.trim()) {
      setError('Please enter a stock ticker')
      return
    }

    // Cancel any existing analysis
    if (abortController) {
      abortController.abort()
    }

    // Reset state
    setIsAnalyzing(true)
    setProgress([])
    setResults(null)
    setError(null)

    // Start analysis with progress streaming
    const controller = analyzeStockWithProgress(
      ticker.toUpperCase(),
      horizon,
      riskProfile,
      // onProgress callback
      (progressData: ProgressData) => {
        console.log('[Frontend] Progress received:', progressData)
        try {
          setProgress(prev => [...prev, progressData])
        } catch (error) {
          console.error('[Frontend] Error updating progress state:', error)
        }
      },
      // onComplete callback
      (data) => {
        console.log('[Frontend] Analysis complete:', data)
        setIsAnalyzing(false)
        setResults(data.data || null)
        setAbortController(null)
      },
      // onError callback
      (err: Error) => {
        console.error('[Frontend] Analysis error:', err)
        console.error('[Frontend] Error stack:', err.stack)
        setIsAnalyzing(false)
        setError(err.message || 'Analysis failed')
        setAbortController(null)
        // Also clear progress to show error state
        if (progress.length === 0) {
          setProgress([{
            step: 'error',
            message: `Error: ${err.message}`,
            timestamp: Date.now()
          }])
        }
      }
    )
    
    setAbortController(controller)
  }

  return (
    <div className="min-vh-100" style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', padding: '20px' }}>
      <Container>
        <header className="text-center text-white mb-5 py-4">
          <h1 className="display-4 fw-bold mb-3">AI-Powered Financial Research Analyst</h1>
          <p className="lead">Generate investment research reports with risk modeling and scenario analysis</p>
        </header>

        <Row className="justify-content-center">
          <Col md={10} lg={8}>
            {/* Input Section */}
            <Card className="mb-4 shadow-lg">
              <Card.Header>
                <h2 className="mb-0">Analysis Parameters</h2>
              </Card.Header>
              <Card.Body>
                <TickerInput 
                  value={ticker}
                  onChange={setTicker}
                />

                <HorizonSelect 
                  value={horizon}
                  onChange={setHorizon}
                />

                <RiskProfileSelect 
                  value={riskProfile}
                  onChange={setRiskProfile}
                />

                <Button
                  variant="primary"
                  size="lg"
                  className="w-100"
                  onClick={handleAnalyze}
                  disabled={isAnalyzing || !ticker.trim()}
                >
                  {isAnalyzing ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      Analyzing...
                    </>
                  ) : (
                    'Run Analysis'
                  )}
                </Button>
                
                {isAnalyzing && abortController && (
                  <Button
                    variant="danger"
                    size="sm"
                    className="w-100 mt-2"
                    onClick={() => {
                      abortController.abort()
                      setIsAnalyzing(false)
                      setError('Analysis cancelled by user')
                      setAbortController(null)
                    }}
                  >
                    Cancel Analysis
                  </Button>
                )}

                {error && (
                  <Alert variant="danger" className="mt-3">
                    {error}
                  </Alert>
                )}
              </Card.Body>
            </Card>

            {/* Progress Display */}
            {isAnalyzing && (
              <ProgressDisplay progress={progress} />
            )}

            {/* Results Display */}
            {results && !isAnalyzing && (
              <ResultsDisplay results={results} />
            )}
          </Col>
        </Row>
      </Container>
    </div>
  )
}

export default App
