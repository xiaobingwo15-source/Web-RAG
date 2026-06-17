import { useState, useCallback, useRef, useEffect } from 'react'
import { useAuth } from './useAuth'
import { streamChat, getThreadMessages, type RetrievalSource, type StreamError, type StreamHandle } from '@/lib/api'
import type { AgentAction, ActionType, ActionSource } from '@/lib/agent-types'
import { LatencyTimer } from '@/lib/performance'

export type ChatMessageRole = 'user' | 'assistant'

export interface ChatReplyTarget {
  id: string
  content: string
  role: ChatMessageRole
}

export interface ChatMessage {
  id?: string
  role: ChatMessageRole
  content: string
  created_at?: string
  images?: string[]
  replyTo?: string  // ID of the message being replied to
  replyToContent?: string  // preview of the quoted message content
  replyToRole?: ChatMessageRole
  thoughts?: string[]
  actions?: AgentAction[]
  sources?: RetrievalSource[]
  adminResponse?: string
}

function parseStoredMessageContent(content: string): { text: string; images?: string[] } {
  try {
    const json = JSON.parse(content)
    if (json && typeof json.text === 'string') {
      return { text: json.text, images: Array.isArray(json.images) ? json.images : [] }
    }
  } catch {
    return { text: content }
  }
  return { text: content }
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [threadId, setThreadId] = useState<string | null>(null)
  const currentThoughts = useRef<string[]>([])
  const currentActionRef = useRef<AgentAction | null>(null)
  const actionIdCounter = useRef(0)
  const tokenBuffer = useRef<string>('')
  const rafId = useRef<number | null>(null)
  const latencyTimer = useRef<LatencyTimer | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const { session } = useAuth()
  const accessToken = session?.access_token

  const flushTokens = useCallback(() => {
    rafId.current = null
    const buffered = tokenBuffer.current
    if (!buffered) return
    tokenBuffer.current = ''
    setMessages((prev) => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      updated[updated.length - 1] = {
        ...last,
        content: last.content + buffered,
      }
      return updated
    })
  }, [])

  useEffect(() => {
    return () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
    }
  }, [])

  const loadThread = useCallback(async (id: string) => {
    if (!accessToken) return
    try {
      const msgs = await getThreadMessages(id, accessToken)
      // Build a lookup map of message ID → content for reply previews
      const contentMap: Record<string, string> = {}
      const roleMap: Record<string, ChatMessageRole> = {}
      for (const m of msgs) {
        const role = m.role === 'user' || m.role === 'assistant' ? m.role : null
        const parsedContent = parseStoredMessageContent(m.content)
        contentMap[m.id] = parsedContent.text
        if (role) roleMap[m.id] = role
      }
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
        const parsedContent = parseStoredMessageContent(m.content)
        parsed.push({
          id: m.id,
          role: m.role as ChatMessageRole,
          content: parsedContent.text,
          created_at: m.created_at,
          images: parsedContent.images,
          replyTo: m.reply_to || undefined,
          replyToContent: m.reply_to ? contentMap[m.reply_to] : undefined,
          replyToRole: m.reply_to ? roleMap[m.reply_to] : undefined,
        })
      }
      setMessages(parsed)
      setThreadId(id)
    } catch (err) {
      console.error('Failed to load thread:', err)
    }
  }, [accessToken])

  const sendMessage = async (
    content: string,
    useDocuments: boolean = false,
    retrievalMode: string = 'hybrid',
    images?: string[],
    replyTo?: string,
    replyToContent?: string,
    replyToRole?: ChatMessageRole,
  ) => {
    if (!accessToken) return

    const now = new Date().toISOString()
    const userClientId = crypto.randomUUID()
    const userMsg: ChatMessage = {
      id: userClientId,
      role: 'user',
      content,
      created_at: now,
      images,
      replyTo,
      replyToContent,
      replyToRole,
    }
    setMessages((prev) => [...prev, userMsg])
    setIsStreaming(true)
    currentThoughts.current = []
    currentActionRef.current = null

    setMessages((prev) => [...prev, { role: 'assistant', content: '', created_at: new Date().toISOString(), thoughts: [], actions: [] }])

    latencyTimer.current = new LatencyTimer('chat.send')
    await streamChat(
      content,
      threadId,
      accessToken,
      (chunk) => {
        if (latencyTimer.current && latencyTimer.current.firstTokenLatency === null) {
          latencyTimer.current.markFirstToken()
        }
        // Transition the last active action to "completed" on first text token
        // so the ThoughtTrace spinner stops while the answer renders
        if (currentActionRef.current) {
          currentActionRef.current = null
          setMessages((prev) => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (!last || last.role !== 'assistant' || !last.actions?.length) return updated
            const actions = last.actions.map(a =>
              a.status === 'active' ? { ...a, status: 'completed' as const } : a
            )
            updated[updated.length - 1] = { ...last, actions }
            return updated
          })
        }
        tokenBuffer.current += chunk
        if (rafId.current === null) {
          rafId.current = requestAnimationFrame(flushTokens)
        }
      },
      (meta) => {
        // Flush any buffered tokens before marking done
        if (rafId.current !== null) {
          cancelAnimationFrame(rafId.current)
          rafId.current = null
        }
        const buffered = tokenBuffer.current
        tokenBuffer.current = ''
        setIsStreaming(false)
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (!last || last.role !== 'assistant') return updated
          let actions = last.actions
          if (actions && actions.length > 0 && currentActionRef.current) {
            actions = [...actions]
            actions[actions.length - 1] = { ...actions[actions.length - 1], status: "completed" }
          }
          updated[updated.length - 1] = {
            ...last,
            content: last.content + buffered,
            ...(meta?.messageId ? { id: meta.messageId } : {}),
            ...(meta?.createdAt ? { created_at: meta.createdAt } : {}),
            actions,
          }
          return updated
        })
        currentActionRef.current = null
        latencyTimer.current?.markDone()
        latencyTimer.current = null
        abortRef.current = null
      },
      (err: StreamError) => {
        console.error('Stream error:', err)
        if (rafId.current !== null) {
          cancelAnimationFrame(rafId.current)
          rafId.current = null
        }
        tokenBuffer.current = ''
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
        latencyTimer.current = null
        abortRef.current = null
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
      (sources) => {
        setMessages((prev) => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'assistant') {
            updated[updated.length - 1] = { ...last, sources }
          }
          return updated
        })
      },
      replyTo,
      (h: StreamHandle) => { abortRef.current = h.abort },
      (meta) => {
        setMessages((prev) => prev.map((message) => {
          if (message.id !== userClientId) return message
          return {
            ...message,
            ...(meta.messageId ? { id: meta.messageId } : {}),
            ...(meta.createdAt ? { created_at: meta.createdAt } : {}),
          }
        }))
      },
    )
  }

  const cancel = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    if (rafId.current !== null) {
      cancelAnimationFrame(rafId.current)
      rafId.current = null
    }
    tokenBuffer.current = ''
    latencyTimer.current = null
    setIsStreaming(false)
  }, [])

  const clearMessages = () => {
    setMessages([])
    setThreadId(null)
  }

  const currentAction = messages.length > 0
    ? messages[messages.length - 1].actions?.find(a => a.status === "active") || null
    : null

  return { messages, sendMessage, isStreaming, threadId, clearMessages, loadThread, currentAction, cancel }
}
