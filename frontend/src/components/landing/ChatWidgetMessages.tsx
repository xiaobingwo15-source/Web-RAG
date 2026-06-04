import { useEffect, useRef } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import type { AnonymousMessage } from '@/hooks/useAnonymousChat'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function ChatWidgetMessages({
  messages,
  isStreaming,
  feedbackMap,
  onFeedback,
}: {
  messages: AnonymousMessage[]
  isStreaming: boolean
  feedbackMap?: Record<string, 1 | -1>
  onFeedback?: (messageId: string, rating: 1 | -1) => void
}) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-4" style={{ backgroundColor: '#EFEAE2' }}>
        <p className="text-center text-sm text-[#667781]">
          Ask me anything about our products and solutions.
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-1" style={{ backgroundColor: '#EFEAE2' }}>
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-[85%] rounded-lg px-2.5 py-1.5 shadow-sm text-[14.2px] leading-[1.35] ${
              msg.role === 'user'
                ? 'bg-bubble-out text-bubble-out-text'
                : 'bg-bubble-in text-bubble-in-text'
            }`}
          >
            {msg.content ? (
              msg.role === 'user' ? (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              ) : (
                <div className="chat-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )
            ) : (
              <div className="flex items-center gap-1">
                <div className="h-2 w-2 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="h-2 w-2 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="h-2 w-2 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            )}
            <div className="flex items-center justify-between mt-0.5">
              <span className="text-[11px] text-[#667781]">
                {new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
              </span>
              {msg.role === 'assistant' && msg.messageId && onFeedback && (
                <div className="flex items-center gap-0.5 ml-2">
                  <button
                    onClick={() => onFeedback(msg.messageId!, 1)}
                    className={`rounded p-0.5 transition-colors cursor-pointer ${
                      feedbackMap?.[msg.messageId] === 1
                        ? 'text-[#00A884] bg-[#00A884]/10'
                        : 'text-[#8696A0] hover:text-[#00A884] hover:bg-[#00A884]/5'
                    }`}
                    title="Good response"
                  >
                    <ThumbsUp className="h-3 w-3" />
                  </button>
                  <button
                    onClick={() => onFeedback(msg.messageId!, -1)}
                    className={`rounded p-0.5 transition-colors cursor-pointer ${
                      feedbackMap?.[msg.messageId] === -1
                        ? 'text-[#EF4444] bg-[#EF4444]/10'
                        : 'text-[#8696A0] hover:text-[#EF4444] hover:bg-[#EF4444]/5'
                    }`}
                    title="Poor response"
                  >
                    <ThumbsDown className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
