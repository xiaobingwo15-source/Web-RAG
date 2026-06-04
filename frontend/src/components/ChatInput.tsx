import { useState, type KeyboardEvent, type ClipboardEvent } from 'react'
import { Send, FileSearch, X, Reply } from 'lucide-react'

export function ChatInput({
  onSend,
  disabled,
  hasDocuments,
  replyTo,
  onCancelReply,
}: {
  onSend: (msg: string, useDocuments: boolean, retrievalMode: string, images?: string[]) => void
  disabled: boolean
  hasDocuments: boolean
  replyTo?: { id: string; content: string } | null
  onCancelReply?: () => void
}) {
  const [value, setValue] = useState('')
  const [useDocuments, setUseDocuments] = useState(true)
  const [images, setImages] = useState<string[]>([])

  const handleSend = () => {
    const trimmed = value.trim()
    if ((!trimmed && images.length === 0) || disabled) return
    onSend(trimmed, hasDocuments && useDocuments, 'hybrid', images.length > 0 ? images : undefined)
    setValue('')
    setImages([])
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items
    if (!items) return

    const imageFiles: File[] = []
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile()
        if (file) imageFiles.push(file)
      }
    }

    if (imageFiles.length === 0) return

    e.preventDefault()

    for (const file of imageFiles) {
      const reader = new FileReader()
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          setImages((prev) => [...prev, reader.result as string])
        }
      }
      reader.readAsDataURL(file)
    }
  }

  const removeImage = (index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="border-t border-border p-4">
      {images.length > 0 && (
        <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2">
          {images.map((src, idx) => (
            <div key={idx} className="relative group">
              <img
                src={src}
                alt={`Pasted ${idx + 1}`}
                className="h-16 w-16 rounded-md border border-border object-cover"
              />
              <button
                onClick={() => removeImage(idx)}
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                title="Remove image"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      {replyTo && (
        <div className="mx-auto flex max-w-3xl items-center gap-2 rounded-t-md border border-b-0 border-primary/30 bg-primary/5 px-3 py-2">
          <Reply className="h-3.5 w-3.5 shrink-0 text-primary" />
          <p className="flex-1 truncate text-xs text-muted-foreground">
            {replyTo.content.length > 120 ? replyTo.content.slice(0, 117) + '...' : replyTo.content}
          </p>
          {onCancelReply && (
            <button onClick={onCancelReply} className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
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
          onPaste={handlePaste}
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
          disabled={disabled || (!value.trim() && images.length === 0)}
          className="rounded-md bg-primary p-2 text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
