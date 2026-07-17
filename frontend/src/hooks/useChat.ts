import { useState, useCallback, useRef, useEffect } from 'react'
import { useAuth } from './useAuth'
import {
  streamChat,
  getThreadMessages,
  type MessageResponse,
  type MessageStatus,
  type RetrievalSource,
  type StreamError,
  type StreamHandle,
} from '@/lib/api'
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
  status: MessageStatus
}

const RESPONSE_POLL_INTERVAL_MS = 3000
const RESPONSE_STALE_AFTER_MS = 135_000
const INTERRUPTED_RESPONSE = 'This response was interrupted. Please try again.'
const EMPTY_RESPONSE = 'The AI returned an empty response. Please try again.'

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

function normalizedStatus(message: MessageResponse): MessageStatus {
  if (message.status === 'streaming' || message.status === 'complete' || message.status === 'failed') {
    return message.status
  }
  return message.role === 'assistant' && !message.content ? 'streaming' : 'complete'
}

function isStale(createdAt?: string): boolean {
  if (!createdAt) return false
  const createdMs = Date.parse(createdAt)
  return Number.isFinite(createdMs) && Date.now() - createdMs >= RESPONSE_STALE_AFTER_MS
}

function hydrateMessages(messages: MessageResponse[]): ChatMessage[] {
  const contentMap: Record<string, string> = {}
  const roleMap: Record<string, ChatMessageRole> = {}

  for (const message of messages) {
    const role = message.role === 'user' || message.role === 'assistant' ? message.role : null
    const parsedContent = parseStoredMessageContent(message.content)
    contentMap[message.id] = parsedContent.text
    if (role) roleMap[message.id] = role
  }

  const hydrated: ChatMessage[] = []
  for (const message of messages) {
    if (message.role === 'admin') {
      const previous = hydrated[hydrated.length - 1]
      if (previous?.role === 'assistant') previous.adminResponse = message.content
      continue
    }

    const parsedContent = parseStoredMessageContent(message.content)
    let status = normalizedStatus(message)
    let content = parsedContent.text
    if (message.role === 'assistant' && status === 'streaming' && isStale(message.created_at)) {
      status = 'failed'
      content = content || INTERRUPTED_RESPONSE
    } else if (message.role === 'assistant' && status === 'failed' && !content) {
      content = INTERRUPTED_RESPONSE
    } else if (message.role === 'assistant' && status === 'complete' && !content) {
      status = 'failed'
      content = EMPTY_RESPONSE
    }

    hydrated.push({
      id: message.id,
      role: message.role as ChatMessageRole,
      content,
      created_at: message.created_at,
      images: parsedContent.images,
      replyTo: message.reply_to || undefined,
      replyToContent: message.reply_to ? contentMap[message.reply_to] : undefined,
      replyToRole: message.reply_to ? roleMap[message.reply_to] : undefined,
      status,
    })
  }
  return hydrated
}

function failPendingResponse(messages: ChatMessage[]): ChatMessage[] {
  const updated = [...messages]
  const last = updated[updated.length - 1]
  if (last?.role === 'assistant') {
    updated[updated.length - 1] = {
      ...last,
      content: last.content || INTERRUPTED_RESPONSE,
      status: 'failed',
    }
  } else if (last?.role === 'user') {
    updated.push({
      role: 'assistant',
      content: INTERRUPTED_RESPONSE,
      created_at: new Date().toISOString(),
      status: 'failed',
    })
  }
  return updated
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
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loadGenerationRef = useRef(0)
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

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearTimeout(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      loadGenerationRef.current += 1
      if (rafId.current !== null) cancelAnimationFrame(rafId.current)
      stopPolling()
      abortRef.current?.()
    }
  }, [stopPolling])

  const loadThread = useCallback(async (id: string) => {
    if (!accessToken) return

    const generation = ++loadGenerationRef.current
    stopPolling()

    try {
      const storedMessages = await getThreadMessages(id, accessToken)
      if (generation !== loadGenerationRef.current) return

      let hydrated = hydrateMessages(storedMessages)
      let latest = hydrated[hydrated.length - 1]
      if (latest?.role === 'user' && isStale(latest.created_at)) {
        hydrated = failPendingResponse(hydrated)
        latest = hydrated[hydrated.length - 1]
      }

      setMessages(hydrated)
      setThreadId(id)

      const pending = latest?.role === 'user'
        || (latest?.role === 'assistant' && latest.status === 'streaming')
      if (!pending) {
        setIsStreaming(false)
        return
      }

      setIsStreaming(true)
      const parsedStartedAt = latest?.created_at ? Date.parse(latest.created_at) : Number.NaN
      const pendingStartedAt = Number.isFinite(parsedStartedAt) ? parsedStartedAt : Date.now()

      const pollPendingResponse = async () => {
        if (generation !== loadGenerationRef.current) return
        try {
          const polled = hydrateMessages(await getThreadMessages(id, accessToken))
          if (generation !== loadGenerationRef.current) return

          let nextMessages = polled
          let nextLatest = nextMessages[nextMessages.length - 1]
          const stillPending = nextLatest?.role === 'user'
            || (nextLatest?.role === 'assistant' && nextLatest.status === 'streaming')
          if (stillPending && Date.now() - pendingStartedAt >= RESPONSE_STALE_AFTER_MS) {
            nextMessages = failPendingResponse(nextMessages)
            nextLatest = nextMessages[nextMessages.length - 1]
          }

          setMessages(nextMessages)
          const terminal = nextLatest?.role === 'assistant' && nextLatest.status !== 'streaming'
          if (terminal) {
            pollRef.current = null
            setIsStreaming(false)
            return
          }
        } catch (error) {
          if (generation !== loadGenerationRef.current) return
          if (Date.now() - pendingStartedAt >= RESPONSE_STALE_AFTER_MS) {
            setMessages((current) => failPendingResponse(current))
            pollRef.current = null
            setIsStreaming(false)
            return
          }
          console.warn('Pending response status check failed; retrying', error)
        }

        pollRef.current = setTimeout(pollPendingResponse, RESPONSE_POLL_INTERVAL_MS)
      }

      pollRef.current = setTimeout(pollPendingResponse, RESPONSE_POLL_INTERVAL_MS)
    } catch (err) {
      if (generation !== loadGenerationRef.current) return
      setIsStreaming(false)
      console.error('Failed to load thread:', err)
    }
  }, [accessToken, stopPolling])

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

    loadGenerationRef.current += 1
    stopPolling()

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
      status: 'complete',
    }
    setMessages((prev) => [...prev, userMsg])
    setIsStreaming(true)
    currentThoughts.current = []
    currentActionRef.current = null

    setMessages((prev) => [...prev, {
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      thoughts: [],
      actions: [],
      status: 'streaming',
    }])

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
          const content = last.content + buffered
          updated[updated.length - 1] = {
            ...last,
            content: content || EMPTY_RESPONSE,
            ...(meta?.messageId ? { id: meta.messageId } : {}),
            ...(meta?.createdAt ? { created_at: meta.createdAt } : {}),
            actions,
            status: content ? 'complete' : 'failed',
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
              status: 'failed',
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
      (meta) => {
        setMessages((prev) => {
          const updated = [...prev]
          for (let index = updated.length - 1; index >= 0; index -= 1) {
            if (updated[index].role !== 'assistant' || updated[index].status !== 'streaming') continue
            updated[index] = {
              ...updated[index],
              ...(meta.messageId ? { id: meta.messageId } : {}),
              ...(meta.createdAt ? { created_at: meta.createdAt } : {}),
            }
            break
          }
          return updated
        })
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
    loadGenerationRef.current += 1
    stopPolling()
    tokenBuffer.current = ''
    latencyTimer.current = null
    setIsStreaming(false)
  }, [stopPolling])

  const clearMessages = () => {
    loadGenerationRef.current += 1
    stopPolling()
    setMessages([])
    setThreadId(null)
  }

  const currentAction = messages.length > 0
    ? messages[messages.length - 1].actions?.find(a => a.status === "active") || null
    : null

  return { messages, sendMessage, isStreaming, threadId, clearMessages, loadThread, currentAction, cancel }
}
