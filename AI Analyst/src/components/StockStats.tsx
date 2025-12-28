import { Card, Row, Col } from 'react-bootstrap'

interface StockStatsProps {
  marketData?: {
    valuation?: {
      current_price?: number
      '52_week_high'?: number
      '52_week_low'?: number
      pe_ratio?: number
      forward_pe?: number
      market_cap?: number
      dividend_yield?: number
      pb_ratio?: number
      ps_ratio?: number
    }
  }
}

function StockStats({ marketData }: StockStatsProps) {
  // Return null if no market data
  if (!marketData?.valuation) {
    return null
  }

  const valuation = marketData.valuation

  // Format currency
  const formatCurrency = (value: number | undefined): string => {
    if (value === undefined || value === null) return 'N/A'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value)
  }

  // Format market cap (B for billions, T for trillions)
  const formatMarketCap = (value: number | undefined): string => {
    if (value === undefined || value === null) return 'N/A'
    if (value >= 1e12) {
      return `$${(value / 1e12).toFixed(2)}T`
    } else if (value >= 1e9) {
      return `$${(value / 1e9).toFixed(2)}B`
    } else if (value >= 1e6) {
      return `$${(value / 1e6).toFixed(2)}M`
    }
    return formatCurrency(value)
  }

  // Format percentage
  const formatPercentage = (value: number | undefined): string => {
    if (value === undefined || value === null) return 'N/A'
    return `${(value * 100).toFixed(2)}%`
  }

  // Format decimal (for ratios)
  const formatDecimal = (value: number | undefined, decimals: number = 2): string => {
    if (value === undefined || value === null) return 'N/A'
    return value.toFixed(decimals)
  }

  // Calculate position in 52-week range (0 to 1)
  const getRangePosition = (): number | null => {
    if (!valuation['52_week_high'] || !valuation['52_week_low'] || !valuation.current_price) {
      return null
    }
    const range = valuation['52_week_high'] - valuation['52_week_low']
    if (range === 0) return null
    return (valuation.current_price - valuation['52_week_low']) / range
  }

  const rangePosition = getRangePosition()

  return (
    <Card className="mb-4 shadow-sm">
      <Card.Header>
        <h3 className="mb-0">Stock Statistics</h3>
      </Card.Header>
      <Card.Body>
        <Row className="g-3">
          {/* Current Price - Prominent */}
          <Col xs={12} md={4}>
            <div className="text-center p-3 bg-light rounded">
              <div className="text-muted small text-uppercase mb-1">Current Price</div>
              <div className="h4 mb-0 fw-bold text-primary">
                {formatCurrency(valuation.current_price)}
              </div>
            </div>
          </Col>

          {/* 52-Week Range */}
          <Col xs={12} md={4}>
            <div className="p-3">
              <div className="text-muted small mb-2">52-Week Range</div>
              <div className="mb-1">
                <span className="fw-semibold">High: </span>
                {formatCurrency(valuation['52_week_high'])}
              </div>
              <div className="mb-2">
                <span className="fw-semibold">Low: </span>
                {formatCurrency(valuation['52_week_low'])}
              </div>
              {/* Visual indicator of position in range */}
              {rangePosition !== null && (
                <div className="position-relative">
                  <div className="progress" style={{ height: '8px' }}>
                    <div
                      className="progress-bar bg-success"
                      role="progressbar"
                      style={{ width: `${rangePosition * 100}%` }}
                      aria-valuenow={rangePosition * 100}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    />
                  </div>
                  <small className="text-muted">
                    {rangePosition > 0.7 ? 'Near high' : rangePosition < 0.3 ? 'Near low' : 'Mid range'}
                  </small>
                </div>
              )}
            </div>
          </Col>

          {/* Market Cap */}
          <Col xs={12} md={4}>
            <div className="text-center p-3 bg-light rounded">
              <div className="text-muted small text-uppercase mb-1">Market Cap</div>
              <div className="h5 mb-0 fw-semibold">
                {formatMarketCap(valuation.market_cap)}
              </div>
            </div>
          </Col>

          {/* Valuation Metrics Row */}
          <Col xs={6} sm={4} md={3}>
            <div className="p-2">
              <div className="text-muted small mb-1">P/E Ratio</div>
              <div className="fw-semibold">{formatDecimal(valuation.pe_ratio)}</div>
            </div>
          </Col>

          {valuation.forward_pe && (
            <Col xs={6} sm={4} md={3}>
              <div className="p-2">
                <div className="text-muted small mb-1">Forward P/E</div>
                <div className="fw-semibold">{formatDecimal(valuation.forward_pe)}</div>
              </div>
            </Col>
          )}

          {valuation.dividend_yield !== undefined && valuation.dividend_yield !== null && valuation.dividend_yield > 0 && (
            <Col xs={6} sm={4} md={3}>
              <div className="p-2">
                <div className="text-muted small mb-1">Dividend Yield</div>
                <div className="fw-semibold text-success">{formatPercentage(valuation.dividend_yield)}</div>
              </div>
            </Col>
          )}

          {valuation.pb_ratio && (
            <Col xs={6} sm={4} md={3}>
              <div className="p-2">
                <div className="text-muted small mb-1">P/B Ratio</div>
                <div className="fw-semibold">{formatDecimal(valuation.pb_ratio)}</div>
              </div>
            </Col>
          )}

          {valuation.ps_ratio && (
            <Col xs={6} sm={4} md={3}>
              <div className="p-2">
                <div className="text-muted small mb-1">P/S Ratio</div>
                <div className="fw-semibold">{formatDecimal(valuation.ps_ratio)}</div>
              </div>
            </Col>
          )}
        </Row>
      </Card.Body>
    </Card>
  )
}

export default StockStats

