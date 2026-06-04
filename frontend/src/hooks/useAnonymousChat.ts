import { useState, useCallback, useRef, useEffect } from 'react'
import { createWidgetSession, resolveTenant, streamWidgetChat, submitWidgetFeedback, type StreamError } from '@/lib/api'

const FREE_TIER_LIMIT = 5

export interface AnonymousMessage {
  role: 'user' | 'assistant'
  content: string
  messageId?: string
}

export function useAnonymousChat() {
  const [messages, setMessages] = useState<AnonymousMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [authError, setAuthError] = useState(false)
  const [limitReached, setLimitReached] = useState(false)
  const [feedbackMap, setFeedbackMap] = useState<Record<string, 1 | -1>>({})
  const threadId = useRef<string | null>(null)
  const sessionRef = useRef<string | null>(null)
  const userMessageCount = useRef(0)
  const tokenBuffer = useRef('')
  const rafId = useRef<number | null>(null)

  const flushTokens = useCallback(() => {
    rafId.current = null
    const buffered = tokenBuffer.current
    if (!buffered) return
    tokenBuffer.current = ''
    setMessages((prev) => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      updated[updated.length - 1] = { ...last, content: last.content + buffered }
      return updated
    })
  }, [])

  useEffect(() => {
    return () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
    }
  }, [])

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
      if (limitReached) return

      const token = await ensureSession()
      if (!token) return

      userMessageCount.current += 1
      setMessages((prev) => [...prev, { role: 'user', content }])
      setIsStreaming(true)
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      await streamWidgetChat(
        content,
        threadId.current,
        token,
        (chunk) => {
          tokenBuffer.current += chunk
          if (rafId.current === null) {
            rafId.current = requestAnimationFrame(flushTokens)
          }
        },
        (msgId?: string) => {
          if (rafId.current !== null) {
            cancelAnimationFrame(rafId.current)
            rafId.current = null
          }
          const buffered = tokenBuffer.current
          tokenBuffer.current = ''
          if (msgId) {
            setMessages((prev) => {
              const updated = [...prev]
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].role === 'assistant' && updated[i].messageId === undefined) {
                  updated[i] = { ...updated[i], messageId: msgId, content: updated[i].content + buffered }
                  break
                }
              }
              return updated
            })
          } else if (buffered) {
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              updated[updated.length - 1] = { ...last, content: last.content + buffered }
              return updated
            })
          }
          setIsStreaming(false)
        },
        (err: StreamError) => {
          if (err.error_code === 'free_tier_limit') {
            setLimitReached(true)
            // Remove the empty assistant placeholder
            setMessages((prev) => prev.slice(0, -1))
            userMessageCount.current -= 1
          } else {
            const errMsg =
              err.error_code === 'rate_limit'
                ? err.message
                : `Sorry, something went wrong: ${err.message}`
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content: last.content || errMsg }
              }
              return updated
            })
          }
          setIsStreaming(false)
        },
        (id) => {
          threadId.current = id
        },
      )

      // Also check frontend count after successful send
      if (userMessageCount.current >= FREE_TIER_LIMIT && !limitReached) {
        setLimitReached(true)
      }
    },
    [ensureSession, limitReached],
  )

  const submitFeedback = useCallback(
    async (messageId: string, rating: 1 | -1) => {
      const token = sessionRef.current
      if (!token || !threadId.current) return
      setFeedbackMap((prev) => ({ ...prev, [messageId]: rating }))
      try {
        await submitWidgetFeedback(threadId.current, messageId, rating, token)
      } catch {
        // Revert on failure
        setFeedbackMap((prev) => {
          const next = { ...prev }
          delete next[messageId]
          return next
        })
      }
    },
    [],
  )

  const preWarmSession = useCallback(() => {
    // Fire and forget — populates sessionRef.current for the first sendMessage
    ensureSession()
  }, [ensureSession])

  return { messages, sendMessage, isStreaming, authError, limitReached, feedbackMap, submitFeedback, preWarmSession }
}
