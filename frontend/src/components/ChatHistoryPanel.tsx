import { useState } from 'react'
import { Plus, MessageSquare, Trash2, Search } from 'lucide-react'
import type { ThreadSummary } from '@/lib/api'
import type { ChatMessage } from '@/hooks/useChat'

interface ChatHistoryPanelProps {
  threads: ThreadSummary[]
  selectedThreadId: string | null
  onSelectThread: (threadId: string) => void
  onDeleteThread: (threadId: string) => void
  onNewChat: () => void
  messages?: ChatMessage[]
}

export function ChatHistoryPanel({
  threads,
  selectedThreadId,
  onSelectThread,
  onDeleteThread,
  onNewChat,
  messages: _messages,
}: ChatHistoryPanelProps) {
  const [searchQuery, setSearchQuery] = useState('')

  const filteredThreads = threads.filter((thread) =>
    thread.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <aside className="flex w-80 flex-col border-l border-border bg-surface shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-medium text-foreground">History</h2>
        <button
          onClick={onNewChat}
          className="p-1.5 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
          title="New chat"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg bg-muted pl-10 pr-4 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none border-none"
          />
        </div>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto">
        {filteredThreads.length === 0 ? (
          <div className="text-center py-8 text-sm text-muted-foreground">
            {searchQuery ? 'No matching conversations' : 'No past conversations'}
          </div>
        ) : (
          filteredThreads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              className={`group flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors border-b border-border/50 ${
                selectedThreadId === thread.id
                  ? 'bg-muted'
                  : 'hover:bg-muted/50'
              }`}
            >
              <MessageSquare className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-foreground truncate">{thread.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
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
                className="rounded-full p-1.5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all cursor-pointer"
                title="Delete thread"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
