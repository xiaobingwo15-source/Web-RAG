import { useState } from 'react'
import { Search, Trash2, MessageSquare } from 'lucide-react'
import type { ThreadSummary } from '@/lib/api'

interface ChatThreadListProps {
  threads: ThreadSummary[]
  selectedThreadId: string | null
  onSelectThread: (threadId: string) => void
  onDeleteThread: (threadId: string) => void
}

export function ChatThreadList({
  threads,
  selectedThreadId,
  onSelectThread,
  onDeleteThread,
}: ChatThreadListProps) {
  const [searchQuery, setSearchQuery] = useState('')

  const filteredThreads = threads.filter((thread) =>
    thread.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <>
      {/* Search Bar */}
      <div className="px-3 py-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#8696A0]" />
          <input
            type="text"
            placeholder="Search or start new chat"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-lg bg-[#F0F2F5] pl-10 pr-4 py-2 text-sm text-[#111B21] placeholder:text-[#8696A0] focus:outline-none border-none"
          />
        </div>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto">
        {filteredThreads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <MessageSquare className="h-10 w-10 text-[#D1D5DB] mb-3" />
            <p className="text-sm text-[#667781] text-center">
              {searchQuery ? 'No conversations found' : 'No conversations yet'}
            </p>
          </div>
        ) : (
          filteredThreads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              className={`group flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors border-b border-[#E9EDEF] ${
                selectedThreadId === thread.id
                  ? 'bg-[#F0F2F5]'
                  : 'hover:bg-[#F5F6F6]'
              }`}
            >
              {/* Avatar */}
              <div className="h-12 w-12 rounded-full bg-[#DFE5E7] flex items-center justify-center shrink-0">
                <MessageSquare className="h-5 w-5 text-[#667781]" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <h3 className="text-[15px] font-normal text-[#111B21] truncate">
                    {thread.title}
                  </h3>
                  <span className="text-xs text-[#667781] shrink-0 ml-2">
                    {new Date(thread.created_at).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </span>
                </div>
                <p className="text-[13px] text-[#667781] truncate mt-0.5">
                  {new Date(thread.created_at).toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>

              {/* Delete button (on hover) */}
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDeleteThread(thread.id)
                }}
                className="rounded-full p-1.5 opacity-0 group-hover:opacity-100 text-[#8696A0] hover:text-[#EF4444] hover:bg-red-50 transition-all cursor-pointer"
                title="Delete thread"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </>
  )
}
