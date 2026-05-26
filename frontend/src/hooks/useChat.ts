import { useState } from 'react'
import { useAuth } from './useAuth'
import { streamChat } from '@/lib/api'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)
  const { session } = useAuth()

  const sendMessage = async (content: string, useDocuments: boolean = false) => {
    if (!session?.access_token) return

    const userMsg: ChatMessage = { role: 'user', content }
    setMessages((prev) => [...prev, userMsg])
    setIsStreaming(true)

    setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

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
      (err) => {
        console.error('Stream error:', err)
        setIsStreaming(false)
      },
      (id) => setThreadId(id),
      useDocuments,
    )
  }

  const clearMessages = () => {
    setMessages([])
    setThreadId(null)
  }

  return { messages, sendMessage, isStreaming, threadId, clearMessages }
}
