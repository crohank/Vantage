import { Form } from 'react-bootstrap'

type Horizon = 'short' | 'medium' | 'long'

interface HorizonSelectProps {
  value: Horizon
  onChange: (value: Horizon) => void
}

function HorizonSelect({ value, onChange }: HorizonSelectProps) {
  return (
    <Form.Group className="mb-3">
      <Form.Label htmlFor="horizon">Time Horizon</Form.Label>
      <Form.Select
        id="horizon"
        value={value}
        onChange={(e) => onChange(e.target.value as Horizon)}
      >
        <option value="short">Short Term</option>
        <option value="medium">Medium Term</option>
        <option value="long">Long Term</option>
      </Form.Select>
    </Form.Group>
  )
}

export default HorizonSelect

