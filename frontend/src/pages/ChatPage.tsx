import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChat, type ChatReplyTarget } from '@/hooks/useChat'
import { useDocuments } from '@/hooks/useDocuments'
import { useThreads } from '@/hooks/useThreads'
import { useAuth } from '@/hooks/useAuth'
import { isAdmin } from '@/lib/roles'
import { submitFeedback, getThreadFeedback } from '@/lib/api'
import { ChatSidebar } from '@/components/ChatSidebar'
import { ChatMessage } from '@/components/ChatMessage'
import { ChatInput } from '@/components/ChatInput'
import { ChatThreadList } from '@/components/ChatThreadList'
import { markInteraction, markRouteReady } from '@/lib/performance'
import {
  MessageSquare,
  LogOut,
  Clock,
  AlertTriangle,
  Download,
  Copy,
  FileText
} from 'lucide-react'

export function ChatPage() {
  const { messages, sendMessage, isStreaming, threadId, clearMessages, loadThread, currentAction } = useChat()
  const {
    documents,
    uploadDocument,
    isUploading,
    hasProcessed,
    duplicateWarning,
    clearDuplicateWarning,
    uploadFailure,
    clearUploadFailure
  } = useDocuments()
  const { threads, selectedThreadId, setSelectedThreadId, refreshThreads, removeThread } = useThreads()
  const { user, session, role, status, signOut } = useAuth()
  const navigate = useNavigate()
  const admin = isAdmin(role || user?.email)
  const accessToken = session?.access_token
  const [feedbackMap, setFeedbackMap] = useState<Record<string, 1 | -1>>({})
  const [replyTo, setReplyTo] = useState<ChatReplyTarget | null>(null)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [showDocUpload, setShowDocUpload] = useState(false)
  const messageViewportRef = useRef<HTMLDivElement>(null)
  const latestMessageRef = useRef<HTMLDivElement>(null)
  const shouldFollowScrollRef = useRef(true)
  const pendingJumpToBottomRef = useRef(false)
  const previousMessageCountRef = useRef(0)

  useEffect(() => {
    markRouteReady('/chat')
  }, [])

  const isNearBottom = useCallback(() => {
    const viewport = messageViewportRef.current
    if (!viewport) return true
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
    return distanceFromBottom < 96
  }, [])

  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    requestAnimationFrame(() => {
      latestMessageRef.current?.scrollIntoView({ behavior, block: 'end' })
    })
  }, [])

  const handleMessageScroll = useCallback(() => {
    shouldFollowScrollRef.current = isNearBottom()
  }, [isNearBottom])

  useEffect(() => {
    const messageCountChanged = messages.length !== previousMessageCountRef.current
    previousMessageCountRef.current = messages.length

    if (pendingJumpToBottomRef.current) {
      pendingJumpToBottomRef.current = false
      shouldFollowScrollRef.current = true
      scrollToLatest('auto')
      return
    }

    if (messages.length === 0) return

    if (messageCountChanged) {
      shouldFollowScrollRef.current = true
      scrollToLatest('smooth')
      return
    }

    if (isStreaming && shouldFollowScrollRef.current) {
      scrollToLatest('auto')
    }
  }, [messages, isStreaming, scrollToLatest])

  const handleLogout = async () => {
    await signOut()
    navigate('/login')
  }

  const handleNewChat = () => {
    clearMessages()
    setSelectedThreadId(null)
    setFeedbackMap({})
    setReplyTo(null)
    shouldFollowScrollRef.current = true
    previousMessageCountRef.current = 0
  }

  const handleSelectThread = async (tid: string) => {
    setSelectedThreadId(tid)
    setReplyTo(null)
    shouldFollowScrollRef.current = true
    pendingJumpToBottomRef.current = true
    await loadThread(tid)
    if (accessToken) {
      try {
        const feedback = await getThreadFeedback(tid, accessToken)
        setFeedbackMap(feedback)
      } catch {
        setFeedbackMap({})
      }
    }
  }

  const handleFeedback = useCallback(async (messageId: string, rating: 1 | -1) => {
    const feedbackThreadId = selectedThreadId || threadId
    if (!accessToken || !feedbackThreadId) return
    setFeedbackMap((prev) => ({ ...prev, [messageId]: rating }))
    try {
      await submitFeedback(feedbackThreadId, messageId, rating, accessToken)
    } catch (err) {
      console.error('Failed to submit feedback:', err)
    }
  }, [accessToken, selectedThreadId, threadId])

  const handleDeleteThread = async (tid: string) => {
    await removeThread(tid)
    if (selectedThreadId === tid) handleNewChat()
  }

  const handleReply = useCallback((target: ChatReplyTarget) => {
    setReplyTo(target)
  }, [])

  const handleSendMessage = async (content: string, useDocuments: boolean = false, retrievalMode: string = 'hybrid', images?: string[]) => {
    const activeReply = replyTo
    shouldFollowScrollRef.current = true
    markInteraction('chat.send', { use_documents: useDocuments, retrieval_mode: retrievalMode })
    setReplyTo(null)
    await sendMessage(content, useDocuments, retrievalMode, images, activeReply?.id, activeReply?.content, activeReply?.role)
    refreshThreads()
  }

  const exportToMarkdown = () => {
    if (messages.length === 0) return
    let md = `# Chat Record - ${new Date().toLocaleString()}\n\n`
    messages.forEach((msg) => {
      md += `### ${msg.role === 'user' ? 'User' : 'Assistant'}\n${msg.content}\n\n`
    })
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat_${selectedThreadId ?? 'new'}.md`
    a.click()
    URL.revokeObjectURL(url)
    setShowExportMenu(false)
  }

  const exportToJSON = () => {
    if (messages.length === 0) return
    const blob = new Blob([JSON.stringify(messages, null, 2)], { type: 'application/json;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat_${selectedThreadId ?? 'new'}.json`
    a.click()
    URL.revokeObjectURL(url)
    setShowExportMenu(false)
  }

  const copyToClipboard = () => {
    if (messages.length === 0) return
    let text = ''
    messages.forEach((msg) => {
      text += `[${msg.role === 'user' ? 'User' : 'Assistant'}]: ${msg.content}\n\n`
    })
    navigator.clipboard.writeText(text)
    setShowExportMenu(false)
  }

  const selectedThread = threads.find((t) => t.id === selectedThreadId)

  if (status === 'pending') {
    return (
      <div className="flex h-screen bg-background items-center justify-center">
        <div className="text-center max-w-md p-8">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <Clock className="h-7 w-7 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">Account Pending Approval</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Your account has been created successfully. An administrator will review and approve your access shortly.
          </p>
          <button onClick={handleLogout} className="text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
            Sign out
          </button>
        </div>
      </div>
    )
  }

  if (status === 'suspended') {
    return (
      <div className="flex h-screen bg-background items-center justify-center">
        <div className="text-center max-w-md p-8">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-7 w-7 text-destructive" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">Account Suspended</h2>
          <p className="text-sm text-muted-foreground mb-6">
            Your account has been suspended. Please contact your administrator for more information.
          </p>
          <button onClick={handleLogout} className="text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
            Sign out
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background">
      {/* ── Left Sidebar: WhatsApp-style thread list ── */}
      <aside className="flex w-80 lg:w-96 flex-col bg-surface border-r border-border shrink-0">
        {/* Sidebar Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-primary text-primary-foreground">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-white/20 flex items-center justify-center">
              <span className="text-sm font-semibold text-white">
                {user?.email?.[0].toUpperCase() ?? 'U'}
              </span>
            </div>
            <span className="text-sm font-medium">{admin ? 'Admin' : 'Chat'}</span>
          </div>
          <button
            onClick={handleNewChat}
            className="p-2 rounded-full hover:bg-white/10 transition-colors cursor-pointer"
            title="New chat"
          >
            <MessageSquare className="h-5 w-5" />
          </button>
        </div>

        {/* Thread List */}
        <ChatThreadList
          threads={threads}
          selectedThreadId={selectedThreadId}
          onSelectThread={handleSelectThread}
          onDeleteThread={handleDeleteThread}
        />

        {/* Admin: Collapsible Document Upload */}
        {admin && (
          <div className="border-t border-border">
            <button
              onClick={() => setShowDocUpload(!showDocUpload)}
              className="flex items-center justify-between w-full px-4 py-3 text-sm font-medium text-foreground hover:bg-sidebar-hover transition-colors cursor-pointer"
            >
              <span>Knowledge Base</span>
              <svg
                className={`h-4 w-4 text-muted-foreground transition-transform ${showDocUpload ? 'rotate-180' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showDocUpload && (
              <div className="px-4 pb-4 max-h-64 overflow-y-auto">
                <ChatSidebar
                  documents={documents}
                  isUploading={isUploading}
                  onUpload={uploadDocument}
                  duplicateWarning={duplicateWarning}
                  onDismissWarning={clearDuplicateWarning}
                  uploadFailure={uploadFailure}
                  onDismissFailure={clearUploadFailure}
                  compact
                />
              </div>
            )}
          </div>
        )}

        {/* User Footer */}
        <div className="mt-auto border-t border-border px-4 py-3 bg-surface">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-sm font-semibold text-primary">
                {user?.email?.[0].toUpperCase() ?? 'U'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">{user?.email ?? 'User'}</p>
              <p className="text-xs text-muted-foreground truncate">{admin ? 'Administrator' : 'Client'}</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Right Panel: Chat Area ── */}
      <main className="flex flex-1 flex-col min-w-0">
        {/* Chat Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-wa-header text-white border-b border-primary/20">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-full bg-white/20 flex items-center justify-center shrink-0">
              <MessageSquare className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-medium truncate">
                {selectedThread?.title ?? (messages.length > 0 ? 'Current Chat' : 'New Chat')}
              </h2>
              <p className="text-xs text-white/70">
                {isStreaming ? 'typing...' : selectedThread ? 'online' : ''}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {/* Export menu */}
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                className="p-2 rounded-full hover:bg-white/10 transition-colors cursor-pointer"
                title="Export chat"
              >
                <Download className="h-5 w-5" />
              </button>
              {showExportMenu && messages.length > 0 && (
                <div className="absolute top-full right-0 mt-1 w-48 rounded-lg border border-border bg-surface p-1 shadow-lg z-20">
                  <button onClick={copyToClipboard} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors">
                    <Copy className="h-4 w-4 text-muted-foreground" />
                    Copy transcript
                  </button>
                  <button onClick={exportToMarkdown} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    Save as Markdown
                  </button>
                  <button onClick={exportToJSON} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors">
                    <Download className="h-4 w-4 text-muted-foreground" />
                    Save as JSON
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Messages Area */}
        <div className="flex flex-1 overflow-hidden">
          <div
            ref={messageViewportRef}
            onScroll={handleMessageScroll}
            className="flex-1 overflow-y-auto"
            style={{ backgroundColor: '#EFEAE2' }}
          >
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <div className="text-center px-6">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/60 mb-4">
                    <MessageSquare className="h-8 w-8 text-[#667781]" />
                  </div>
                  <h2 className="text-lg font-medium text-[#111B21] mb-1">Web RAG Chat</h2>
                  <p className="text-sm text-[#667781]">
                    {admin
                      ? hasProcessed
                        ? 'Ask a question about your documents'
                        : 'Upload documents or start a conversation'
                      : 'Start a conversation'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="px-4 py-3 space-y-1 max-w-4xl mx-auto">
                {messages.map((msg, i) => (
                  <ChatMessage
                    key={i}
                    message={msg}
                    messageId={msg.id}
                    feedback={msg.id && msg.role === 'assistant' ? feedbackMap[msg.id] ?? null : null}
                    onFeedback={msg.id && msg.role === 'assistant' ? handleFeedback : undefined}
                    onReply={handleReply}
                  />
                ))}

                {isStreaming && !currentAction && !(messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content) && (
                  <div className="flex items-start gap-2">
                    <div className="bg-bubble-in rounded-lg px-3 py-2 shadow-sm max-w-[65%]">
                      <div className="flex items-center gap-1">
                        <div className="h-2 w-2 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="h-2 w-2 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="h-2 w-2 rounded-full bg-[#8696A0] animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                )}

                <div ref={latestMessageRef} className="h-px" />
              </div>
            )}
          </div>

        </div>

        {/* Chat Input */}
        <ChatInput
          onSend={handleSendMessage}
          disabled={isStreaming}
          hasDocuments={hasProcessed}
          replyTo={replyTo}
          onCancelReply={() => setReplyTo(null)}
        />
      </main>
    </div>
  )
}
