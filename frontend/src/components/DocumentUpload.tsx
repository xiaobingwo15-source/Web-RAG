import { useRef, useState, type DragEvent } from 'react'
import { Upload, FileText, CheckCircle, XCircle, Loader2, AlertTriangle } from 'lucide-react'
import type { DocumentStatus } from '@/lib/api'

const ACCEPTED_TYPES = ['.pdf', '.md', '.txt']

export function DocumentUpload({
  documents,
  isUploading,
  onUpload,
  duplicateWarning,
  onDismissWarning,
}: {
  documents: DocumentStatus[]
  isUploading: boolean
  onUpload: (file: File, useOcr?: boolean) => void
  duplicateWarning?: string | null
  onDismissWarning?: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [useOcr, setUseOcr] = useState(false)

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file, useOcr)
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onUpload(file, useOcr)
    if (inputRef.current) inputRef.current.value = ''
  }

  const statusIcon = (status: string) => {
    switch (status) {
      case 'processed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      default:
        return <Loader2 className="h-4 w-4 animate-spin text-yellow-500" />
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {duplicateWarning && (
        <div className="flex items-start gap-2 rounded-md border border-yellow-500/30 bg-yellow-500/10 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-500" />
          <div className="flex-1">
            <p className="text-sm text-yellow-200">{duplicateWarning}</p>
          </div>
          {onDismissWarning && (
            <button onClick={onDismissWarning} className="text-yellow-400 hover:text-yellow-200">
              <XCircle className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => inputRef.current?.click()}
        className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-6 text-center transition-colors hover:border-primary/50"
      >
        {isUploading ? (
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        ) : (
          <Upload className="h-8 w-8 text-muted-foreground" />
        )}
        <p className="text-sm text-muted-foreground">
          {isUploading ? 'Uploading...' : 'Drop documents here or click to browse'}
        </p>
        <p className="text-xs text-muted-foreground">
          PDF, Markdown, or Text files
        </p>
        <label
          className="flex items-center gap-2 text-xs text-muted-foreground"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={useOcr}
            onChange={(e) => setUseOcr(e.target.checked)}
            className="h-3 w-3 rounded border-border"
          />
          Use OCR (for complex PDFs)
        </label>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {documents.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-foreground">Uploaded Documents</h4>
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="rounded-md border border-border px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate text-sm text-foreground">
                  {doc.metadata?.title || doc.filename}
                </span>
                {statusIcon(doc.status)}
              </div>
              {doc.metadata?.tags && doc.metadata.tags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {doc.metadata.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                    >
                      {tag}
                    </span>
                  ))}
                  {doc.metadata?.language && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
                      {doc.metadata.language}
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
