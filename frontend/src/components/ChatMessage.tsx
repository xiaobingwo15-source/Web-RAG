import { useEffect, useState } from 'react'
import type { ChatMessage as ChatMessageType, ChatReplyTarget } from '@/hooks/useChat'
import { ThoughtTrace } from '@/components/ThoughtTrace'
import { BookOpen, Shield, ThumbsUp, ThumbsDown, Reply } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface ChatMessageProps {
  message: ChatMessageType
  messageId?: string
  feedback?: 1 | -1 | null
  onFeedback?: (messageId: string, rating: 1 | -1) => void
  onReply?: (target: ChatReplyTarget) => void
}

function replyAuthor(role: ChatMessageType['replyToRole']) {
  if (role === 'user') return 'You'
  if (role === 'assistant') return 'Assistant'
  return 'Message'
}

function formatMessageTime(createdAt?: string) {
  if (!createdAt) return '--:--'
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return '--:--'
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ChatMessage({ message, messageId, feedback, onFeedback, onReply }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const normalizedFeedback = feedback ?? null
  const [localFeedback, setLocalFeedback] = useState<1 | -1 | null>(normalizedFeedback)
  const canReply = Boolean(message.content && messageId && onReply)

  useEffect(() => {
    setLocalFeedback(normalizedFeedback)
  }, [messageId, normalizedFeedback])

  const handleFeedback = (rating: 1 | -1) => {
    const newRating = localFeedback === rating ? null : rating
    setLocalFeedback(newRating)
    if (newRating && messageId && onFeedback) {
      onFeedback(messageId, newRating)
    }
  }

  const timestamp = formatMessageTime(message.created_at)

  const handleReply = () => {
    if (!messageId || !message.content || !onReply) return
    onReply({ id: messageId, content: message.content, role: message.role })
  }

  return (
    <div className={`group flex ${isUser ? 'justify-end' : 'justify-start'} mb-1`}>
      <div className={`flex max-w-[86%] items-center gap-1.5 sm:max-w-[72%] ${isUser ? 'flex-row-reverse' : ''}`}>
        <div className="min-w-0">
        {/* Thought trace (assistant only) */}
        {!isUser && ((message.thoughts && message.thoughts.length > 0) || (message.actions && message.actions.length > 0)) && (
          <ThoughtTrace thoughts={message.thoughts} actions={message.actions} />
        )}

        {/* Bubble */}
        <div
          className={`relative rounded-lg px-2.5 py-1.5 shadow-sm ${
            isUser
              ? 'bg-bubble-out text-bubble-out-text'
              : 'bg-bubble-in text-bubble-in-text'
          }`}
        >
          {/* Reply-to preview */}
          {message.replyToContent && (
            <div
              className={`mb-1.5 overflow-hidden rounded-md border-l-4 border-[#00A884] px-2.5 py-1.5 ${
                isUser ? 'bg-white/65' : 'bg-[#F0F2F5]'
              }`}
            >
              <p className="text-[11px] font-semibold leading-tight text-[#008069]">
                Replying to {replyAuthor(message.replyToRole)}
              </p>
              <p className="mt-0.5 line-clamp-2 break-words text-xs leading-snug text-[#54656F]">
                {message.replyToContent}
              </p>
            </div>
          )}

          {/* Images */}
          {isUser && message.images && message.images.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-1.5">
              {message.images.map((src, idx) => (
                <img
                  key={idx}
                  src={src}
                  alt={`Pasted image ${idx + 1}`}
                  className="max-w-[200px] max-h-[200px] rounded-md object-contain"
                />
              ))}
            </div>
          )}

          {/* Content */}
          {message.content && (
            isUser ? (
              <p className="whitespace-pre-wrap text-[14.2px] leading-[1.35]">{message.content}</p>
            ) : (
              <div className="chat-markdown text-[14.2px]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              </div>
            )
          )}

          {/* Timestamp (inside bubble, bottom-right) */}
          <span className={`block text-right text-[11px] mt-0.5 ${isUser ? 'text-[#667781]' : 'text-[#667781]'}`}>
            {timestamp}
          </span>
        </div>

        {/* Admin response */}
        {!isUser && message.adminResponse && (
          <div className="mt-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1">
              <Shield className="h-3 w-3 text-amber-600" />
              <span className="text-[11px] font-semibold text-amber-700">Admin Response</span>
            </div>
            <p className="whitespace-pre-wrap text-[13px] text-[#111B21]">
              {message.adminResponse}
            </p>
          </div>
        )}

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-1.5 rounded-lg bg-white border border-[#E9EDEF] px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1.5">
              <BookOpen className="h-3 w-3 text-[#00A884]" />
              <span className="text-[11px] font-semibold text-[#111B21]">Sources</span>
            </div>
            <div className="space-y-1.5">
              {message.sources.slice(0, 5).map((source, index) => (
                <div key={`${source.chunk_id}-${index}`} className="rounded bg-[#F5F6F6] px-2.5 py-1.5">
                  <div className="flex items-center justify-between gap-2 text-[11px]">
                    <span className="truncate font-medium text-[#111B21]">
                      {source.filename || `Document ${source.document_id.slice(0, 8)}`}
                    </span>
                    <span className="shrink-0 text-[#667781]">
                      {source.retrieval_mode} · {source.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-[12px] text-[#667781]">
                    {source.snippet}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Feedback buttons (assistant only) */}
        {!isUser && message.content && messageId && (
          <div className="mt-0.5 flex items-center gap-0.5">
            <button
              onClick={() => handleFeedback(1)}
              className={`rounded p-1 transition-colors cursor-pointer ${
                localFeedback === 1
                  ? 'text-[#00A884] bg-[#00A884]/10'
                  : 'text-[#8696A0] hover:text-[#00A884] hover:bg-[#00A884]/5'
              }`}
              title="Good response"
              aria-label="Good response"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => handleFeedback(-1)}
              className={`rounded p-1 transition-colors cursor-pointer ${
                localFeedback === -1
                  ? 'text-[#EF4444] bg-[#EF4444]/10'
                  : 'text-[#8696A0] hover:text-[#EF4444] hover:bg-[#EF4444]/5'
              }`}
              title="Poor response"
              aria-label="Poor response"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        </div>

        {canReply && (
          <button
            onClick={handleReply}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/90 text-[#54656F] shadow-sm transition hover:bg-white hover:text-[#00A884] focus:outline-none focus:ring-2 focus:ring-[#00A884]/30 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 cursor-pointer"
            title="Reply"
            aria-label="Reply to this message"
          >
            <Reply className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  )
}
