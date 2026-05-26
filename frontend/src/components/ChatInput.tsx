import { useState, type KeyboardEvent } from 'react'
import { Send, FileSearch } from 'lucide-react'

export function ChatInput({
  onSend,
  disabled,
  hasDocuments,
}: {
  onSend: (msg: string, useDocuments: boolean) => void
  disabled: boolean
  hasDocuments: boolean
}) {
  const [value, setValue] = useState('')
  const [useDocuments, setUseDocuments] = useState(true)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, hasDocuments && useDocuments)
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
