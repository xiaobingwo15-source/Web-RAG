import { useAuth } from '@/hooks/useAuth'
import { useNavigate } from 'react-router-dom'
import { LogOut, Database } from 'lucide-react'
import { DocumentUpload } from './DocumentUpload'
import type { DocumentStatus } from '@/lib/api'

interface ChatSidebarProps {
  documents: DocumentStatus[]
  isUploading: boolean
  onUpload: (file: File, useOcr?: boolean) => void
  duplicateWarning?: string | null
  onDismissWarning?: () => void
}

export function ChatSidebar({
  documents,
  isUploading,
  onUpload,
  duplicateWarning,
  onDismissWarning,
}: ChatSidebarProps) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <aside className="flex w-72 flex-col border-r border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Database className="h-5 w-5 text-primary" />
        <h2 className="font-semibold text-foreground text-sm">Knowledge Base</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <DocumentUpload
          documents={documents}
          isUploading={isUploading}
          onUpload={onUpload}
          duplicateWarning={duplicateWarning}
          onDismissWarning={onDismissWarning}
        />
      </div>

      <div className="border-t border-border p-4 bg-muted/40">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
            <span className="text-xs font-semibold text-primary">
              {user?.email?.[0].toUpperCase() ?? 'U'}
            </span>
          </div>
          <div className="flex-1 truncate">
            <p className="truncate text-xs font-medium text-foreground">
              {user?.email ?? 'User'}
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
  )
}
