import type { ChatMessage as ChatMessageType } from '@/hooks/useChat'
import { ThoughtTrace } from '@/components/ThoughtTrace'

export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[80%]">
        {!isUser && message.thoughts && message.thoughts.length > 0 && (
          <ThoughtTrace thoughts={message.thoughts} />
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
            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
          )}
        </div>
      </div>
    </div>
  )
}
