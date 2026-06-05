import { useEffect, useRef, useState, type KeyboardEvent, type ClipboardEvent } from 'react'
import type { ChatReplyTarget } from '@/hooks/useChat'
import { Send, FileSearch, X } from 'lucide-react'

function replyAuthor(role: ChatReplyTarget['role']) {
  return role === 'user' ? 'You' : 'Assistant'
}

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
  replyTo?: ChatReplyTarget | null
  onCancelReply?: () => void
}) {
  const [value, setValue] = useState('')
  const [useDocuments, setUseDocuments] = useState(true)
  const [images, setImages] = useState<string[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (replyTo) {
      textareaRef.current?.focus()
    }
  }, [replyTo])

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

  const hasContent = value.trim().length > 0 || images.length > 0

  return (
    <div className="bg-[#F0F2F5] px-3 py-2">
      {/* Pasted images preview */}
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 px-1">
          {images.map((src, idx) => (
            <div key={idx} className="relative group">
              <img
                src={src}
                alt={`Pasted ${idx + 1}`}
                className="h-16 w-16 rounded-lg border border-[#E9EDEF] object-cover"
              />
              <button
                onClick={() => removeImage(idx)}
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[#EF4444] text-white opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                title="Remove"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Reply preview */}
      {replyTo && (
        <div className="mb-2 flex items-center gap-3 rounded-lg border border-[#D8E8E4] bg-white px-3 py-2 shadow-sm">
          <div className="h-11 w-1 rounded-full bg-[#00A884] shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-[#008069]">Replying to {replyAuthor(replyTo.role)}</p>
            <p className="mt-0.5 line-clamp-2 break-words text-xs leading-snug text-[#54656F]">
              {replyTo.content}
            </p>
          </div>
          {onCancelReply && (
            <button
              onClick={onCancelReply}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[#54656F] hover:bg-[#F0F2F5] hover:text-[#111B21] cursor-pointer"
              title="Cancel reply"
              aria-label="Cancel reply"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2">
        {/* RAG toggle */}
        {hasDocuments && (
          <button
            onClick={() => setUseDocuments((prev) => !prev)}
            title={useDocuments ? 'RAG mode ON — answers from documents' : 'RAG mode OFF — general chat'}
            className={`p-2.5 rounded-full transition-colors shrink-0 cursor-pointer ${
              useDocuments
                ? 'text-[#00A884] bg-[#00A884]/10'
                : 'text-[#54656F] hover:bg-[#E9EDEF]'
            }`}
          >
            <FileSearch className="h-5 w-5" />
          </button>
        )}

        {/* Text input */}
        <div className="flex-1 flex items-end bg-white rounded-lg border-none overflow-hidden">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={disabled}
            rows={1}
            placeholder={
              hasDocuments && useDocuments
                ? 'Ask about your documents...'
                : 'Type a message'
            }
            className="flex-1 resize-none border-none bg-transparent px-3 py-2.5 text-[15px] text-[#111B21] placeholder:text-[#8696A0] focus:outline-none disabled:opacity-50 min-h-[42px] max-h-[150px]"
            style={{ lineHeight: '1.35' }}
          />
        </div>

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={disabled || !hasContent}
          className={`p-2.5 rounded-full transition-colors shrink-0 cursor-pointer ${
            hasContent && !disabled
              ? 'text-[#00A884] hover:bg-[#00A884]/10'
              : 'text-[#54656F]'
          } disabled:opacity-50`}
        >
          <Send className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}
