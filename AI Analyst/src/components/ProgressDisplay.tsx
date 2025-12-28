import { useEffect, useRef } from 'react'
import { Card, ListGroup } from 'react-bootstrap'
import { ProgressData } from '../services/api'

interface ProgressDisplayProps {
  progress: ProgressData[]
}

function ProgressDisplay({ progress }: ProgressDisplayProps) {
  const progressEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new progress arrives
  useEffect(() => {
    progressEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [progress])

  const getVariant = (step: string): string => {
    const stepLower = step.toLowerCase()
    if (stepLower.includes('error')) return 'danger'
    if (stepLower.includes('ok') || stepLower.includes('complete')) return 'success'
    if (stepLower.includes('market') || stepLower.includes('macro') || stepLower.includes('risk') || stepLower.includes('scenario') || stepLower.includes('memo')) return 'info'
    return 'secondary'
  }

  return (
    <Card className="mb-4 shadow">
      <Card.Header>
        <h3 className="mb-0">Analysis Progress</h3>
      </Card.Header>
      <Card.Body>
        <div style={{ maxHeight: '400px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '0.9rem' }}>
          {progress.length === 0 ? (
            <div className="text-muted">Starting analysis...</div>
          ) : (
            <ListGroup variant="flush">
              {progress.map((item, index) => (
                <ListGroup.Item
                  key={index}
                  variant={getVariant(item.step) as any}
                  className="d-flex justify-content-between align-items-start"
                >
                  <div className="flex-grow-1">
                    <small className="text-muted me-3">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </small>
                    <span>{item.message}</span>
                  </div>
                </ListGroup.Item>
              ))}
            </ListGroup>
          )}
          <div ref={progressEndRef} />
        </div>
      </Card.Body>
    </Card>
  )
}

export default ProgressDisplay

