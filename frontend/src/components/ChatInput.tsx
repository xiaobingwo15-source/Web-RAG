import { useState, type KeyboardEvent } from 'react'
import { Send, FileSearch } from 'lucide-react'

const RETRIEVAL_MODES = ['vector', 'fts', 'hybrid'] as const
const RETRIEVAL_LABELS: Record<string, string> = {
  vector: 'Vector',
  fts: 'FTS',
  hybrid: 'Hybrid',
}

export function ChatInput({
  onSend,
  disabled,
  hasDocuments,
}: {
  onSend: (msg: string, useDocuments: boolean, retrievalMode: string) => void
  disabled: boolean
  hasDocuments: boolean
}) {
  const [value, setValue] = useState('')
  const [useDocuments, setUseDocuments] = useState(true)
  const [retrievalMode, setRetrievalMode] = useState<string>('hybrid')

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, hasDocuments && useDocuments, retrievalMode)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="border-t border-border p-4">
      {hasDocuments && useDocuments && (
        <div className="mx-auto mb-2 flex max-w-3xl items-center gap-1">
          <span className="text-xs text-muted-foreground">Retrieval:</span>
          {RETRIEVAL_MODES.map((mode) => (
            <button
              key={mode}
              onClick={() => setRetrievalMode(mode)}
              className={`rounded-md px-2 py-0.5 text-xs transition-colors ${
                retrievalMode === mode
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              {RETRIEVAL_LABELS[mode]}
            </button>
          ))}
        </div>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        {hasDocuments && (
          <button
            onClick={() => setUseDocuments((prev) => !prev)}
            title={useDocuments ? 'RAG mode ON — answers from documents' : 'RAG mode OFF — general chat'}
            className={`rounded-md p-2 transition-colors ${
              useDocuments
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            <FileSearch className="h-4 w-4" />
          </button>
        )}
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          placeholder={
            hasDocuments && useDocuments
              ? 'Ask a question about your documents...'
              : 'Type a message... (Shift+Enter for new line)'
          }
          className="flex-1 resize-none rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="rounded-md bg-primary p-2 text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
