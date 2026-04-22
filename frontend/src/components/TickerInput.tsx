import { Form } from 'react-bootstrap'

interface TickerInputProps {
  value: string
  onChange: (value: string) => void
  resolvedTicker?: string | null
  isResolving?: boolean
}

function TickerInput({ value, onChange, resolvedTicker, isResolving }: TickerInputProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target.value

    // If input looks like a ticker (only uppercase letters/numbers, no spaces),
    // auto-uppercase it. Otherwise, allow natural language input as-is.
    const isTickerLike = /^[A-Za-z0-9-]*$/.test(input) && !input.includes(' ')
    onChange(isTickerLike ? input.toUpperCase() : input)
  }

  return (
    <Form.Group className="mb-3">
      <Form.Label htmlFor="ticker">Stock Ticker or Question</Form.Label>
      <Form.Control
        id="ticker"
        type="text"
        value={value}
        onChange={handleChange}
        placeholder="e.g., AAPL or 'How is Apple doing?'"
        maxLength={200}
      />
      {isResolving && (
        <Form.Text className="text-info">
          <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
          Resolving ticker...
        </Form.Text>
      )}
      {resolvedTicker && !isResolving && (
        <Form.Text className="text-success">
          Resolved to: <strong>{resolvedTicker}</strong>
        </Form.Text>
      )}
    </Form.Group>
  )
}

export default TickerInput
