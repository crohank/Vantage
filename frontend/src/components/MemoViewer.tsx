import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Copy, Check } from 'lucide-react'
import { Button } from './ui/button'

interface MemoViewerProps {
  memo: string
}

function MemoViewer({ memo }: MemoViewerProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(memo)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* noop */
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={handleCopy}>
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy memo'}
        </Button>
      </div>
      <article className="prose prose-sm dark:prose-invert max-w-none max-h-[640px] overflow-y-auto rounded-md border border-border bg-surface-elevated/30 p-5 prose-headings:font-semibold prose-headings:tracking-tight prose-h1:text-[20px] prose-h2:text-[16px] prose-h3:text-[14px] prose-p:text-[13px] prose-p:leading-relaxed prose-li:text-[13px] prose-code:font-mono prose-code:text-[12px] prose-strong:text-foreground">
        <ReactMarkdown>{memo}</ReactMarkdown>
      </article>
    </div>
  )
}

export default MemoViewer
