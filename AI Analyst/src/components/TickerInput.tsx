import { Form } from 'react-bootstrap'

interface TickerInputProps {
  value: string
  onChange: (value: string) => void
}

function TickerInput({ value, onChange }: TickerInputProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Auto-uppercase and alphanumeric only
    const upperValue = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '')
    onChange(upperValue)
  }

  return (
    <Form.Group className="mb-3">
      <Form.Label htmlFor="ticker">Stock Ticker</Form.Label>
      <Form.Control
        id="ticker"
        type="text"
        value={value}
        onChange={handleChange}
        placeholder="e.g., AAPL, MSFT, TSLA"
        maxLength={10}
      />
    </Form.Group>
  )
}

export default TickerInput

