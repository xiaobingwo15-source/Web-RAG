import { useState } from 'react'
import { MessageCircle, X } from 'lucide-react'
import { useAnonymousChat } from '@/hooks/useAnonymousChat'
import { ChatWidgetMessages } from './ChatWidgetMessages'
import { ChatWidgetInput } from './ChatWidgetInput'
import { markInteraction } from '@/lib/performance'

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const { messages, sendMessage, isStreaming, authError, limitReached, feedbackMap, submitFeedback, preWarmSession } = useAnonymousChat()

  return (
    <>
      {open && (
        <div className="fixed bottom-6 right-6 z-50 flex h-[500px] w-96 flex-col rounded-lg border border-border bg-card shadow-2xl opacity-100 scale-100 transition-all duration-200">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-semibold text-foreground">
              Web RAG Assistant
            </span>
            <button
              onClick={() => {
                markInteraction('widget.close')
                setOpen(false)
              }}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {authError ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-4">
              <p className="text-center text-sm text-muted-foreground">
                Chat is unavailable right now. Please try again later.
              </p>
            </div>
          ) : (
            <>
              <ChatWidgetMessages messages={messages} isStreaming={isStreaming} feedbackMap={feedbackMap} onFeedback={submitFeedback} />
              {limitReached ? (
                <div className="border-t border-border bg-[#F0F2F5] px-4 py-4 text-center">
                  <p className="text-sm text-[#667781] mb-3">
                    You've reached the free question limit.
                  </p>
                  <a
                    href="/login"
                    className="inline-block rounded-lg bg-[#00A884] px-5 py-2 text-sm font-medium text-white hover:bg-[#008F72] transition-colors"
                  >
                    Sign up to continue
                  </a>
                </div>
              ) : (
                <ChatWidgetInput onSend={sendMessage} disabled={isStreaming} />
              )}
            </>
          )}
        </div>
      )}

      {!open && (
        <button
          onClick={() => {
            markInteraction('widget.open')
            setOpen(true)
            preWarmSession()
          }}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-all hover:scale-105 hover:opacity-90"
        >
          <MessageCircle className="h-6 w-6" />
        </button>
      )}
    </>
  )
}
