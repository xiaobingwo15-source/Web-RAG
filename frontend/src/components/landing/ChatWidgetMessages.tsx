import { useEffect, useRef } from 'react'
import type { AnonymousMessage } from '@/hooks/useAnonymousChat'
import ReactMarkdown from 'react-markdown'

export function ChatWidgetMessages({
  messages,
  isStreaming,
}: {
  messages: AnonymousMessage[]
  isStreaming: boolean
}) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <p className="text-center text-sm text-muted-foreground">
          Ask me anything about our products and solutions.
        </p>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
              msg.role === 'user'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground'
            }`}
          >
            {msg.content ? (
              msg.role === 'user' ? (
                msg.content
              ) : (
                <div className="chat-markdown">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              )
            ) : (
              <span className="inline-block animate-pulse">...</span>
            )}
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
