import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChat } from '@/hooks/useChat'
import { useDocuments } from '@/hooks/useDocuments'
import { useThreads } from '@/hooks/useThreads'
import { useAuth } from '@/hooks/useAuth'
import { isAdmin } from '@/lib/roles'
import { submitFeedback, getThreadFeedback } from '@/lib/api'
import { ChatSidebar } from '@/components/ChatSidebar'
import { ChatMessage } from '@/components/ChatMessage'
import { ChatInput } from '@/components/ChatInput'
import { ChatHistoryPanel } from '@/components/ChatHistoryPanel'
import { markInteraction, markRouteReady } from '@/lib/performance'
import { PanelRightOpen, PanelRightClose, MessageSquare, User, LogOut, Clock, AlertTriangle } from 'lucide-react'

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
  const [showPanel, setShowPanel] = useState(true)
  const [feedbackMap, setFeedbackMap] = useState<Record<string, 1 | -1>>({})
  const [replyTo, setReplyTo] = useState<{ id: string; content: string } | null>(null)

  useEffect(() => {
    markRouteReady('/chat')
  }, [])

  const handleLogout = async () => {
    await signOut()
    navigate('/login')
  }

  // Pending approval screen
  if (status === 'pending') {
    return (
      <div className="flex h-screen bg-background items-center justify-center">
        <div className="text-center max-w-md p-8">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
            <Clock className="h-7 w-7 text-primary" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">
            Account Pending Approval
          </h2>
          <p className="text-sm text-muted-foreground mb-6">
            Your account has been created successfully. An administrator will review and approve your access shortly.
          </p>
          <button
            onClick={handleLogout}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Sign out
          </button>
        </div>
      </div>
    )
  }

  // Suspended screen
  if (status === 'suspended') {
    return (
      <div className="flex h-screen bg-background items-center justify-center">
        <div className="text-center max-w-md p-8">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-destructive/10 border border-destructive/20">
            <AlertTriangle className="h-7 w-7 text-destructive" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">
            Account Suspended
          </h2>
          <p className="text-sm text-muted-foreground mb-6">
            Your account has been suspended. Please contact your administrator for more information.
          </p>
          <button
            onClick={handleLogout}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Sign out
          </button>
        </div>
      </div>
    )
  }

  const handleNewChat = () => {
    clearMessages()
    setSelectedThreadId(null)
    setFeedbackMap({})
    setReplyTo(null)
  }

  const handleSelectThread = async (threadId: string) => {
    setSelectedThreadId(threadId)
    setReplyTo(null)
    await loadThread(threadId)
    // Load existing feedback for this thread
    if (session?.access_token) {
      try {
        const feedback = await getThreadFeedback(threadId, session!.access_token)
        setFeedbackMap(feedback)
      } catch {
        setFeedbackMap({})
      }
    }
  }

  const handleFeedback = useCallback(async (messageId: string, rating: 1 | -1) => {
    const feedbackThreadId = selectedThreadId || threadId
    if (!session?.access_token || !feedbackThreadId) return
    setFeedbackMap((prev) => ({ ...prev, [messageId]: rating }))
    try {
      await submitFeedback(feedbackThreadId, messageId, rating, session!.access_token)
    } catch (err) {
      console.error('Failed to submit feedback:', err)
    }
  }, [session?.access_token, selectedThreadId, threadId])

  const handleDeleteThread = async (threadId: string) => {
    await removeThread(threadId)
    if (selectedThreadId === threadId) {
      handleNewChat()
    }
  }

  const handleReply = useCallback((messageId: string, content: string) => {
    setReplyTo({ id: messageId, content })
  }, [])

  const handleSendMessage = async (content: string, useDocuments: boolean = false, retrievalMode: string = 'hybrid', images?: string[]) => {
    markInteraction('chat.send', { use_documents: useDocuments, retrieval_mode: retrievalMode })
    await sendMessage(content, useDocuments, retrievalMode, images, replyTo?.id, replyTo?.content)
    setReplyTo(null)
    refreshThreads()
  }

  return (
    <div className="flex h-screen bg-background">
      {admin ? (
        <ChatSidebar
          documents={documents}
          isUploading={isUploading}
          onUpload={uploadDocument}
          duplicateWarning={duplicateWarning}
          onDismissWarning={clearDuplicateWarning}
          uploadFailure={uploadFailure}
          onDismissFailure={clearUploadFailure}
        />
      ) : (
        <aside className="flex w-72 flex-col border-r border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3 bg-muted/10">
            <MessageSquare className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-bold text-foreground">Chat</h2>
          </div>

          <div className="flex-1" />

          <div className="border-t border-border p-4 bg-muted/40">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 ring-2 ring-primary/30">
                <User className="h-4 w-4 text-primary" />
              </div>
              <div className="flex-1 truncate">
                <p className="truncate text-xs font-semibold text-foreground">Client</p>
                <p className="truncate text-[10px] text-muted-foreground">
                  {user?.email ?? 'Unknown'}
                </p>
              </div>
              <button
                onClick={handleLogout}
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </aside>
      )}
      <main className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border px-4 py-2 bg-muted/20">
          <span className="text-sm font-medium text-foreground">
            {admin ? (hasProcessed ? 'Documents loaded' : 'No documents') : 'Chat'}
          </span>
          <button
            onClick={() => {
              markInteraction('chat.history_panel.toggle')
              setShowPanel((prev) => !prev)
            }}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors cursor-pointer"
            title={showPanel ? 'Hide chat history' : 'Show chat history'}
          >
            {showPanel ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </button>
        </div>
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <h2 className="text-xl font-semibold text-foreground">
                    Agentic RAG Masterclass
                  </h2>
                  <p className="mt-2 text-muted-foreground">
                    {admin
                      ? (hasProcessed
                        ? 'Ask a question about your documents'
                        : 'Upload documents or start a conversation')
                      : 'Start a conversation'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="mx-auto max-w-3xl space-y-4">
                {messages.map((msg, i) => {
                  const msgId = msg.id
                  return (
                    <ChatMessage
                      key={i}
                      message={msg}
                      messageId={msgId}
                      threadId={selectedThreadId}
                      feedback={msgId && msg.role === 'assistant' ? feedbackMap[msgId] ?? null : null}
                      onFeedback={msgId && msg.role === 'assistant' ? handleFeedback : undefined}
                      onReply={handleReply}
                    />
                  )
                })}

                {isStreaming && !currentAction && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                    Thinking...
                  </div>
                )}
              </div>
            )}
          </div>
          {showPanel && (
            <ChatHistoryPanel
              threads={threads}
              selectedThreadId={selectedThreadId}
              onSelectThread={handleSelectThread}
              onDeleteThread={handleDeleteThread}
              onNewChat={handleNewChat}
              messages={messages}
            />
          )}
        </div>
        <ChatInput onSend={handleSendMessage} disabled={isStreaming} hasDocuments={hasProcessed} replyTo={replyTo} onCancelReply={() => setReplyTo(null)} />
      </main>
    </div>
  )
}
