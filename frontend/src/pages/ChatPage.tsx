import { useState } from 'react'
import { useChat } from '@/hooks/useChat'
import { useDocuments } from '@/hooks/useDocuments'
import { ChatSidebar } from '@/components/ChatSidebar'
import { ChatMessage } from '@/components/ChatMessage'
import { ChatInput } from '@/components/ChatInput'
import { DocumentUpload } from '@/components/DocumentUpload'
import { PanelRightOpen, PanelRightClose } from 'lucide-react'

export function ChatPage() {
  const { messages, sendMessage, isStreaming, clearMessages } = useChat()
  const { documents, uploadDocument, isUploading, hasProcessed } = useDocuments()
  const [showPanel, setShowPanel] = useState(false)

  return (
    <div className="flex h-screen bg-background">
      <ChatSidebar onNewChat={clearMessages} />
      <main className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <span className="text-sm font-medium text-foreground">
            {hasProcessed ? 'Documents loaded' : 'No documents'}
          </span>
          <button
            onClick={() => setShowPanel((prev) => !prev)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"
            title={showPanel ? 'Hide documents panel' : 'Show documents panel'}
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
                    {hasProcessed
                      ? 'Ask a question about your documents'
                      : 'Upload documents or start a conversation'}
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
            <div className="w-80 overflow-y-auto border-l border-border p-4">
              <h3 className="mb-4 text-sm font-semibold text-foreground">
                Document Upload
              </h3>
              <DocumentUpload
                documents={documents}
                isUploading={isUploading}
                onUpload={uploadDocument}
              />
            </div>
          )}
        </div>
        <ChatInput onSend={sendMessage} disabled={isStreaming} hasDocuments={hasProcessed} />
      </main>
    </div>
  )
}
