import { useState, useCallback, useRef } from 'react'
import { useAuth } from './useAuth'
import { streamChat, getThreadMessages, type StreamError } from '@/lib/api'
import type { AgentAction, ActionType, ActionSource } from '@/lib/agent-types'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  thoughts?: string[]
  actions?: AgentAction[]
  adminResponse?: string
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)
  const currentThoughts = useRef<string[]>([])
  const currentActionRef = useRef<AgentAction | null>(null)
  const actionIdCounter = useRef(0)
  const { session } = useAuth()

  const loadThread = useCallback(async (id: string) => {
    if (!session?.access_token) return
    try {
      const msgs = await getThreadMessages(id, session.access_token)
      const parsed: ChatMessage[] = []
      for (const m of msgs) {
        if (m.role === 'admin') {
          // Attach admin response to the preceding assistant message
          const prev = parsed[parsed.length - 1]
          if (prev && prev.role === 'assistant') {
            prev.adminResponse = m.content
          }
          continue
        }
        try {
          const json = JSON.parse(m.content)
          if (json && typeof json.text === 'string') {
            parsed.push({
              role: m.role as 'user' | 'assistant',
              content: json.text,
              images: json.images || [],
            })
            continue
          }
        } catch {}
        parsed.push({ role: m.role as 'user' | 'assistant', content: m.content })
      }
      setMessages(parsed)
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
    currentActionRef.current = null

    setMessages((prev) => [...prev, { role: 'assistant', content: '', thoughts: [], actions: [] }])

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
      () => {
        setIsStreaming(false)
        if (currentActionRef.current) {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last.actions && last.actions.length > 0) {
              const actions = [...last.actions]
              actions[actions.length - 1] = { ...actions[actions.length - 1], status: "completed" }
              updated[updated.length - 1] = { ...last, actions }
            }
            return updated
          })
          currentActionRef.current = null
        }
      },
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
              actions: last.actions?.map(a => ({ ...a, status: "completed" as const })),
            }
          }
          return updated
        })
        currentActionRef.current = null
        setIsStreaming(false)
      },
      (id) => setThreadId(id),
      useDocuments,
      retrievalMode,
      images,
      (thought, actionMeta?) => {
        currentThoughts.current.push(thought)

        if (actionMeta) {
          actionIdCounter.current += 1
          const newAction: AgentAction = {
            id: `action-${actionIdCounter.current}`,
            type: actionMeta.type as ActionType,
            source: actionMeta.source as ActionSource,
            content: thought,
            data: actionMeta.data,
            timestamp: Date.now(),
            status: "active",
          }

          currentActionRef.current = newAction

          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            
            let actions = last.actions ? [...last.actions] : []
            actions = actions.map(a => 
              a.status === 'active' ? { ...a, status: 'completed' as const } : a
            )
            actions.push(newAction)

            updated[updated.length - 1] = {
              ...last,
              actions,
              thoughts: [...currentThoughts.current],
            }
            return updated
          })
        } else {
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            updated[updated.length - 1] = {
              ...last,
              thoughts: [...currentThoughts.current],
            }
            return updated
          })
        }
      },
    )
  }

  const clearMessages = () => {
    setMessages([])
    setThreadId(null)
  }

  const currentAction = messages.length > 0
    ? messages[messages.length - 1].actions?.find(a => a.status === "active") || null
    : null

  return { messages, sendMessage, isStreaming, threadId, clearMessages, loadThread, currentAction }
}
