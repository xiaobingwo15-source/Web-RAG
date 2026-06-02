import { useState, useCallback, useRef } from 'react'
import { createWidgetSession, resolveTenant, streamWidgetChat, type StreamError } from '@/lib/api'

export interface AnonymousMessage {
  role: 'user' | 'assistant'
  content: string
}

export function useAnonymousChat() {
  const [messages, setMessages] = useState<AnonymousMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [authError, setAuthError] = useState(false)
  const threadId = useRef<string | null>(null)
  const sessionRef = useRef<string | null>(null)

  const ensureSession = useCallback(async (): Promise<string | null> => {
    if (sessionRef.current) return sessionRef.current

    try {
      const tenant = await resolveTenant()
      const { token } = await createWidgetSession(tenant.slug)
      sessionRef.current = token
      return token
    } catch {
      setAuthError(true)
      return null
    }
  }, [])

  const sendMessage = useCallback(
    async (content: string) => {
      const token = await ensureSession()
      if (!token) return

      setMessages((prev) => [...prev, { role: 'user', content }])
      setIsStreaming(true)
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      await streamWidgetChat(
        content,
        threadId.current,
        token,
        (chunk) => {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = {
              ...last,
              content: last.content + chunk,
            }
            return updated
          })
        },
        () => setIsStreaming(false),
        (err: StreamError) => {
          const message =
            err.error_code === 'rate_limit'
              ? err.message
              : `Sorry, something went wrong: ${err.message}`
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = { ...last, content: last.content || message }
            }
            return updated
          })
          setIsStreaming(false)
        },
        (id) => {
          threadId.current = id
        },
      )
    },
    [ensureSession],
  )

  return { messages, sendMessage, isStreaming, authError }
}
