import { Form } from 'react-bootstrap'

type RiskProfile = 'conservative' | 'moderate' | 'aggressive'

interface RiskProfileSelectProps {
  value: RiskProfile
  onChange: (value: RiskProfile) => void
}

function RiskProfileSelect({ value, onChange }: RiskProfileSelectProps) {
  return (
    <Form.Group className="mb-3">
      <Form.Label htmlFor="risk-profile">Risk Profile</Form.Label>
      <Form.Select
        id="risk-profile"
        value={value}
        onChange={(e) => onChange(e.target.value as RiskProfile)}
      >
        <option value="conservative">Conservative</option>
        <option value="moderate">Moderate</option>
        <option value="aggressive">Aggressive</option>
      </Form.Select>
    </Form.Group>
  )
}

export default RiskProfileSelect

