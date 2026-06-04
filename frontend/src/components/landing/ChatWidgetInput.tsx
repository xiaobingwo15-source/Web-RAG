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
    <div className="flex items-end gap-2 bg-[#F0F2F5] px-3 py-2">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        placeholder="Type a message"
        className="flex-1 resize-none rounded-lg border-none bg-white px-3 py-2.5 text-[15px] text-[#111B21] placeholder:text-[#8696A0] focus:outline-none disabled:opacity-50 min-h-[42px]"
        style={{ lineHeight: '1.35' }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className={`p-2.5 rounded-full transition-colors cursor-pointer ${
          value.trim() && !disabled
            ? 'text-[#00A884] hover:bg-[#00A884]/10'
            : 'text-[#54656F]'
        } disabled:opacity-50`}
      >
        <Send className="h-5 w-5" />
      </button>
    </div>
  )
}
