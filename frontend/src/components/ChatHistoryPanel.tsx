import { useState } from 'react'
import { Plus, MessageSquare, Trash2, Download, Copy, Search, FileText } from 'lucide-react'
import type { ThreadSummary } from '@/lib/api'
import type { ChatMessage } from '@/hooks/useChat'

interface ChatHistoryPanelProps {
  threads: ThreadSummary[]
  selectedThreadId: string | null
  onSelectThread: (threadId: string) => void
  onDeleteThread: (threadId: string) => void
  onNewChat: () => void
  messages: ChatMessage[]
}

export function ChatHistoryPanel({
  threads,
  selectedThreadId,
  onSelectThread,
  onDeleteThread,
  onNewChat,
  messages,
}: ChatHistoryPanelProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [showExportMenu, setShowExportMenu] = useState(false)

  const filteredThreads = threads.filter((thread) =>
    thread.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const exportToMarkdown = () => {
    if (messages.length === 0) return
    let mdContent = `# Chat Record - ${new Date().toLocaleString()}\n\n`
    messages.forEach((msg) => {
      const roleName = msg.role === 'user' ? 'User' : 'Assistant'
      mdContent += `### ${roleName}\n${msg.content}\n\n`
    })

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)
    link.setAttribute('download', `chat_record_${selectedThreadId ?? 'new'}.md`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setShowExportMenu(false)
  }

  const exportToJSON = () => {
    if (messages.length === 0) return
    const jsonContent = JSON.stringify(messages, null, 2)
    const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.setAttribute('href', url)
    link.setAttribute('download', `chat_record_${selectedThreadId ?? 'new'}.json`)
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setShowExportMenu(false)
  }

  const copyToClipboard = () => {
    if (messages.length === 0) return
    let text = ''
    messages.forEach((msg) => {
      const roleName = msg.role === 'user' ? 'User' : 'Assistant'
      text += `[${roleName}]: ${msg.content}\n\n`
    })
    navigator.clipboard.writeText(text)
    alert('Conversation transcript copied to clipboard!')
    setShowExportMenu(false)
  }

  return (
    <aside className="flex w-80 flex-col border-l border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-semibold text-foreground text-sm">Conversation History</h2>
      </div>

      <div className="p-4 space-y-3 border-b border-border">
        <button
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 transition-colors font-medium"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>

        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border border-border bg-input pl-9 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-1">
        {filteredThreads.length === 0 ? (
          <div className="text-center py-8 text-xs text-muted-foreground">
            {searchQuery ? 'No matching conversations' : 'No past conversations'}
          </div>
        ) : (
          filteredThreads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              className={`group flex items-center gap-2 rounded-md px-3 py-2.5 text-xs cursor-pointer transition-colors ${
                selectedThreadId === thread.id
                  ? 'bg-muted text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
              }`}
            >
              <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground group-hover:text-foreground" />
              <div className="flex-1 min-w-0">
                <p className="truncate pr-1">{thread.title}</p>
                <p className="text-[10px] text-muted-foreground/80 mt-0.5 font-normal">
                  {new Date(thread.created_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDeleteThread(thread.id)
                }}
                className="rounded p-1 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-muted-foreground/10 transition-all"
                title="Delete thread"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>

      {messages.length > 0 && (
        <div className="border-t border-border p-4 bg-muted/20">
          <div className="relative">
            <button
              onClick={() => setShowExportMenu((prev) => !prev)}
              className="flex w-full items-center justify-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-xs font-medium text-foreground hover:bg-muted transition-colors"
            >
              <Download className="h-4 w-4" />
              Export / Output Chat
            </button>

            {showExportMenu && (
              <div className="absolute bottom-full left-0 mb-2 w-full rounded-md border border-border bg-popover p-1 shadow-md z-10 animate-in fade-in slide-in-from-bottom-2 duration-150">
                <button
                  onClick={copyToClipboard}
                  className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs text-foreground hover:bg-muted transition-colors"
                >
                  <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                  Copy Transcript
                </button>
                <button
                  onClick={exportToMarkdown}
                  className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs text-foreground hover:bg-muted transition-colors"
                >
                  <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  Save as Markdown (.md)
                </button>
                <button
                  onClick={exportToJSON}
                  className="flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-xs text-foreground hover:bg-muted transition-colors"
                >
                  <Download className="h-3.5 w-3.5 text-muted-foreground" />
                  Save as JSON (.json)
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  )
}
