import { Card } from 'react-bootstrap'
import ReactMarkdown from 'react-markdown'

interface MemoViewerProps {
  memo: string
}

function MemoViewer({ memo }: MemoViewerProps) {
  return (
    <Card className="mt-3">
      <Card.Body>
        <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
          <ReactMarkdown>{memo}</ReactMarkdown>
        </div>
      </Card.Body>
    </Card>
  )
}

export default MemoViewer

