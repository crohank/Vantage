import { useState } from 'react'
import { Card, Badge, Button, ListGroup } from 'react-bootstrap'
import ScenarioCard from './ScenarioCard'
import MemoViewer from './MemoViewer'
import StockStats from './StockStats'
import { AnalysisResults } from '../services/api'

interface ResultsDisplayProps {
  results: AnalysisResults
}

function ResultsDisplay({ results }: ResultsDisplayProps) {
  const [showMemo, setShowMemo] = useState(false)

  const recommendation = results?.recommendation || 'N/A'
  const confidence = results?.confidence_score || 0
  const scenarios = results?.scenarios || {}
  const memo = results?.memo || ''

  const getRecommendationVariant = (): 'success' | 'danger' | 'warning' => {
    if (recommendation === 'Buy') return 'success'
    if (recommendation === 'Sell') return 'danger'
    return 'warning'
  }

  const variant = getRecommendationVariant()

  return (
    <Card className="mb-4 shadow">
      <Card.Header>
        <h2 className="mb-0">Analysis Results</h2>
      </Card.Header>
      <Card.Body>
        {/* Stock Statistics Section */}
        <StockStats marketData={results?.market_data} />

        {/* Recommendation Section */}
        <Card className={`border-${variant} mb-4`}>
          <Card.Body className="text-center">
            <div className="text-muted text-uppercase small mb-2">Recommendation</div>
            <Badge bg={variant} className="fs-3 px-4 py-2 mb-3">
              {recommendation}
            </Badge>
            <div className="mb-2">
              <strong>Confidence: {(confidence * 100).toFixed(0)}%</strong>
            </div>
            <div className="progress mb-0" style={{ height: '8px' }}>
              <div 
                className={`progress-bar bg-${variant}`}
                role="progressbar"
                style={{ width: `${confidence * 100}%` }}
                aria-valuenow={confidence * 100}
                aria-valuemin={0}
                aria-valuemax={100}
              />
            </div>
          </Card.Body>
        </Card>

        {/* Scenarios Section */}
        {Object.keys(scenarios).length > 0 && (
          <div className="mb-4">
            <h3 className="mb-3">Scenarios</h3>
            <div className="row g-3">
              {Object.entries(scenarios).map(([name, data]) => (
                <div key={name} className="col-md-4">
                  <ScenarioCard
                    name={name}
                    returnValue={data.return || 0}
                    probability={data.prob || 0}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Memo Section */}
        {memo && (
          <div className="mb-4">
            <Button
              variant="primary"
              onClick={() => setShowMemo(!showMemo)}
              className="w-100"
            >
              {showMemo ? 'Hide' : 'Show'} Investment Memo
            </Button>
            {showMemo && <MemoViewer memo={memo} />}
          </div>
        )}

        {/* Timing Section */}
        {results?.timing && (
          <div>
            <h3 className="mb-3">Timing Breakdown</h3>
            <ListGroup>
              {Object.entries(results.timing).map(([step, duration]) => (
                <ListGroup.Item key={step} className="d-flex justify-content-between">
                  <span className="fw-semibold">{step}</span>
                  <span className="text-primary">
                    {duration >= 60
                      ? `${Math.floor(duration / 60)}m ${(duration % 60).toFixed(1)}s`
                      : `${duration.toFixed(1)}s`
                    }
                  </span>
                </ListGroup.Item>
              ))}
            </ListGroup>
          </div>
        )}
      </Card.Body>
    </Card>
  )
}

export default ResultsDisplay

