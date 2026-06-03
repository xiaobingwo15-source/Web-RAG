import { useState, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'
import { markInteraction } from '@/lib/performance'

export function ChatWidgetInput({
  onSend,
  disabled,
}: {
  onSend: (msg: string) => void
  disabled: boolean
}) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    markInteraction('widget.send')
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex items-end gap-2 border-t border-border p-3">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder="Ask about our solutions..."
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
  )
}
