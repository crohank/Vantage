import { useEffect, useState } from 'react'
import { ListGroup } from 'react-bootstrap'
import { useNavigate } from 'react-router-dom'
import { fetchAnalyses, AnalysisRecord } from '../services/api'

function RecentAnalyses() {
  const [items, setItems] = useState<AnalysisRecord[]>([])
  const navigate = useNavigate()

  useEffect(() => {
    fetchAnalyses({ limit: 10 }).then(setItems).catch(() => undefined)
  }, [])

  return (
    <ListGroup variant="flush">
      {items.map((item) => (
        <ListGroup.Item
          key={item._id}
          action
          onClick={() => navigate(`/analyse/${item._id}`)}
          className="small"
        >
          <div className="fw-semibold">{item.ticker}</div>
          <div className="text-muted">{item.recommendation} {item.createdAt ? `- ${new Date(item.createdAt).toLocaleDateString()}` : ''}</div>
        </ListGroup.Item>
      ))}
      {items.length === 0 && (
        <ListGroup.Item className="text-muted small">
          No analyses yet.
        </ListGroup.Item>
      )}
    </ListGroup>
  )
}

export default RecentAnalyses
