import { useState } from 'react'
import { useChat } from '@/hooks/useChat'
import { useDocuments } from '@/hooks/useDocuments'
import { useThreads } from '@/hooks/useThreads'
import { useAuth } from '@/hooks/useAuth'
import { isAdmin } from '@/lib/roles'
import { ChatSidebar } from '@/components/ChatSidebar'
import { ChatMessage } from '@/components/ChatMessage'
import { ChatInput } from '@/components/ChatInput'
import { ChatHistoryPanel } from '@/components/ChatHistoryPanel'
import { PanelRightOpen, PanelRightClose } from 'lucide-react'

export function ChatPage() {
  const { messages, sendMessage, isStreaming, clearMessages, loadThread } = useChat()
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
  const { user, role } = useAuth()
  const admin = isAdmin(role || user?.email)
  const [showPanel, setShowPanel] = useState(true)

  const handleNewChat = () => {
    clearMessages()
    setSelectedThreadId(null)
  }

  const handleSelectThread = (threadId: string) => {
    setSelectedThreadId(threadId)
    loadThread(threadId)
  }

  const handleDeleteThread = async (threadId: string) => {
    await removeThread(threadId)
    if (selectedThreadId === threadId) {
      handleNewChat()
    }
  }

  const handleSendMessage = async (content: string, useDocuments: boolean = false, retrievalMode: string = 'hybrid', images?: string[]) => {
    await sendMessage(content, useDocuments, retrievalMode, images)
    refreshThreads()
  }

  return (
    <div className="flex h-screen bg-background">
      {admin && (
        <ChatSidebar
          documents={documents}
          isUploading={isUploading}
          onUpload={uploadDocument}
          duplicateWarning={duplicateWarning}
          onDismissWarning={clearDuplicateWarning}
          uploadFailure={uploadFailure}
          onDismissFailure={clearUploadFailure}
        />
      )}
      <main className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border px-4 py-2 bg-muted/20">
          <span className="text-sm font-medium text-foreground">
            {admin ? (hasProcessed ? 'Documents loaded' : 'No documents') : 'Chat'}
          </span>
          <button
            onClick={() => setShowPanel((prev) => !prev)}
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
                {messages.map((msg, i) => (
                  <ChatMessage key={i} message={msg} />
                ))}
                {isStreaming && (
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
        <ChatInput onSend={handleSendMessage} disabled={isStreaming} hasDocuments={hasProcessed} />
      </main>
    </div>
  )
}
