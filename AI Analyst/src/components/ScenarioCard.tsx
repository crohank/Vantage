import { Card } from 'react-bootstrap'

interface ScenarioCardProps {
  name: string
  returnValue: number
  probability: number
}

function ScenarioCard({ name, returnValue, probability }: ScenarioCardProps) {
  const returnPercent = (returnValue * 100).toFixed(1)
  const probPercent = (probability * 100).toFixed(0)
  const isPositive = returnValue >= 0

  const getVariant = (): 'success' | 'danger' | 'warning' => {
    const nameLower = name.toLowerCase()
    if (nameLower === 'bull') return 'success'
    if (nameLower === 'bear') return 'danger'
    return 'warning'
  }

  const variant = getVariant()

  return (
    <Card className={`border-${variant} h-100`}>
      <Card.Body className="text-center">
        <Card.Title className={`text-${variant} text-uppercase fw-bold mb-3`}>
          {name}
        </Card.Title>
        <div className={`display-6 fw-bold mb-2 ${isPositive ? 'text-success' : 'text-danger'}`}>
          {isPositive ? '+' : ''}{returnPercent}%
        </div>
        <div className="text-muted">
          {probPercent}% probability
        </div>
      </Card.Body>
    </Card>
  )
}

export default ScenarioCard

