import { DocumentUpload } from './DocumentUpload'
import type { DocumentStatus } from '@/lib/api'

interface ChatSidebarProps {
  documents: DocumentStatus[]
  isUploading: boolean
  onUpload: (files: File[], useOcr?: boolean) => void
  duplicateWarning?: string | null
  onDismissWarning?: () => void
  uploadFailure?: { filename: string; error: string } | null
  onDismissFailure?: () => void
  /** Compact mode: hide header/footer, used inside collapsible sections */
  compact?: boolean
}

export function ChatSidebar({
  documents,
  isUploading,
  onUpload,
  duplicateWarning,
  onDismissWarning,
  uploadFailure,
  onDismissFailure,
  compact = false,
}: ChatSidebarProps) {
  return (
    <div className={compact ? '' : 'flex flex-col h-full'}>
      <DocumentUpload
        documents={documents}
        isUploading={isUploading}
        onUpload={onUpload}
        duplicateWarning={duplicateWarning}
        onDismissWarning={onDismissWarning}
        uploadFailure={uploadFailure}
        onDismissFailure={onDismissFailure}
      />
    </div>
  )
}
