import type { ChatMessage as ChatMessageType } from '@/hooks/useChat'
import { ThoughtTrace } from '@/components/ThoughtTrace'
import { Shield } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={isUser ? "max-w-[80%]" : "w-full max-w-[90%] md:max-w-[85%]"}>
        {!isUser && ((message.thoughts && message.thoughts.length > 0) || (message.actions && message.actions.length > 0)) && (
          <ThoughtTrace thoughts={message.thoughts} actions={message.actions} />
        )}
        <div
          className={`rounded-lg px-4 py-2 ${
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-foreground'
          }`}
        >
          {isUser && message.images && message.images.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
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
          {message.content && (
            isUser ? (
              <p className="whitespace-pre-wrap text-sm">{message.content}</p>
            ) : (
              <div className="chat-markdown text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              </div>
            )
          )}
        </div>
        {!isUser && message.adminResponse && (
          <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
            <div className="flex items-center gap-2 mb-1.5">
              <Shield className="h-3.5 w-3.5 text-amber-500" />
              <span className="text-xs font-semibold text-amber-600">Admin Response</span>
            </div>
            <p className="whitespace-pre-wrap text-sm text-foreground">
              {message.adminResponse}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
