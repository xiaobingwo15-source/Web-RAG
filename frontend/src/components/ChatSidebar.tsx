import { useAuth } from '@/hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { LogOut, Plus, MessageSquare } from 'lucide-react'

export function ChatSidebar({ onNewChat }: { onNewChat: () => void }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <aside className="flex w-64 flex-col border-r border-border bg-card">
      <div className="p-4">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-foreground hover:bg-muted"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        <div className="space-y-1">
          {/* Thread list placeholder — will be populated from Supabase */}
        </div>
      </div>

      <div className="border-t border-border p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted">
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="flex-1 truncate">
            <p className="truncate text-sm text-foreground">
              {user?.email ?? 'User'}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  )
}
