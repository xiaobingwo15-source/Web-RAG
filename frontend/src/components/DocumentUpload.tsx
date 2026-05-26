import { useRef, type DragEvent } from 'react'
import { Upload, FileText, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import type { DocumentStatus } from '@/lib/api'

const ACCEPTED_TYPES = ['.pdf', '.md', '.txt']

export function DocumentUpload({
  documents,
  isUploading,
  onUpload,
}: {
  documents: DocumentStatus[]
  isUploading: boolean
  onUpload: (file: File) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file)
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onUpload(file)
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
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2"
            >
              <FileText className="h-4 w-4 text-muted-foreground" />
              <span className="flex-1 truncate text-sm text-foreground">
                {doc.filename}
              </span>
              {statusIcon(doc.status)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
