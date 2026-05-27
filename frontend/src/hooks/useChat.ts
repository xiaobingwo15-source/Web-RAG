import { useState, useCallback, useRef } from 'react'
import { useAuth } from './useAuth'
import { streamChat, getThreadMessages, type StreamError } from '@/lib/api'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  thoughts?: string[]
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)
  const currentThoughts = useRef<string[]>([])
  const { session } = useAuth()

  const loadThread = useCallback(async (id: string) => {
    if (!session?.access_token) return
    try {
      const msgs = await getThreadMessages(id, session.access_token)
      setMessages(msgs.map((m) => {
        try {
          const parsed = JSON.parse(m.content)
          if (parsed && typeof parsed.text === 'string') {
            return {
              role: m.role as 'user' | 'assistant',
              content: parsed.text,
              images: parsed.images || [],
            }
          }
        } catch {}
        return { role: m.role as 'user' | 'assistant', content: m.content }
      }))
      setThreadId(id)
    } catch (err) {
      console.error('Failed to load thread:', err)
    }
  }, [session?.access_token])

  const sendMessage = async (
    content: string,
    useDocuments: boolean = false,
    retrievalMode: string = 'hybrid',
    images?: string[],
  ) => {
    if (!session?.access_token) return

    const userMsg: ChatMessage = { role: 'user', content, images }
    setMessages((prev) => [...prev, userMsg])
    setIsStreaming(true)
    currentThoughts.current = []

    setMessages((prev) => [...prev, { role: 'assistant', content: '', thoughts: [] }])

    await streamChat(
      content,
      threadId,
      session.access_token,
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
        console.error('Stream error:', err)
        const message = err.error_code === 'rate_limit'
          ? err.message
          : `Sorry, something went wrong: ${err.message}`
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'assistant') {
            updated[updated.length - 1] = {
              ...last,
              content: last.content || message,
            }
          }
          return updated
        })
        setIsStreaming(false)
      },
      (id) => setThreadId(id),
      useDocuments,
      retrievalMode,
      images,
      (thought) => {
        currentThoughts.current.push(thought)
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          updated[updated.length - 1] = {
            ...last,
            thoughts: [...currentThoughts.current],
          }
          return updated
        })
      },
    )
  }

  const clearMessages = () => {
    setMessages([])
    setThreadId(null)
  }

  return { messages, sendMessage, isStreaming, threadId, clearMessages, loadThread }
}
