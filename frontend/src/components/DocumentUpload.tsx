import { useRef, useState, useEffect, type DragEvent } from 'react'
import { Upload, FileText, CheckCircle, XCircle, Loader2, AlertTriangle, Trash2, Eye } from 'lucide-react'
import type { DocumentStatus } from '@/lib/api'
import { DocumentPreviewModal } from './DocumentPreviewModal'

const ACCEPTED_TYPES = ['.pdf', '.md', '.txt', '.csv', '.xlsx', '.xls']

export function DocumentUpload({
  documents,
  isUploading,
  onUpload,
  onDelete,
  duplicateWarning,
  onDismissWarning,
  uploadFailure,
  onDismissFailure,
  token,
}: {
  documents: DocumentStatus[]
  isUploading: boolean
  onUpload: (file: File, useOcr?: boolean) => void
  onDelete?: (documentId: string) => Promise<{ message: string; filename: string }>
  duplicateWarning?: string | null
  onDismissWarning?: () => void
  uploadFailure?: { filename: string; error: string } | null
  onDismissFailure?: () => void
  token?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [useOcr, setUseOcr] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [previewDocId, setPreviewDocId] = useState<string | null>(null)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
    }
  }, [])

  const handleDeleteClick = async (docId: string) => {
    if (!onDelete) return
    if (confirmDeleteId === docId) {
      // Second click — actually delete
      setConfirmDeleteId(null)
      setDeletingId(docId)
      setDeleteError(null)
      try {
        await onDelete(docId)
      } catch (err: any) {
        setDeleteError(err.message || 'Failed to delete document')
      } finally {
        setDeletingId(null)
      }
    } else {
      // First click — enter confirm state
      setDeleteError(null)
      setConfirmDeleteId(docId)
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      confirmTimerRef.current = setTimeout(() => setConfirmDeleteId(null), 3000)
    }
  }

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
      {uploadFailure && (
        <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <div className="flex-1">
            <h5 className="text-xs font-bold text-red-400">Upload Failed</h5>
            <p className="text-xs text-red-200 mt-0.5">
              Failed to process <span className="font-semibold">{uploadFailure.filename}</span>: {uploadFailure.error}
            </p>
          </div>
          {onDismissFailure && (
            <button onClick={onDismissFailure} className="text-red-400 hover:text-red-200">
              <XCircle className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

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

      {deleteError && (
        <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <div className="flex-1">
            <p className="text-xs text-red-200">{deleteError}</p>
          </div>
          <button onClick={() => setDeleteError(null)} className="text-red-400 hover:text-red-200">
            <XCircle className="h-4 w-4" />
          </button>
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
          PDF, Markdown, Text, CSV, or Excel files
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
              className="group rounded-md border border-border px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate text-sm text-foreground">
                  {doc.metadata?.title || doc.filename}
                </span>
                {statusIcon(doc.status)}
                {token && doc.status === 'processed' && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setPreviewDocId(doc.id) }}
                    className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-colors group-hover:opacity-100 hover:text-primary"
                    title="Preview document"
                  >
                    <Eye className="h-4 w-4" />
                  </button>
                )}
                {onDelete && (
                  deletingId === doc.id ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteClick(doc.id) }}
                      className={`h-4 w-4 shrink-0 transition-colors ${
                        confirmDeleteId === doc.id
                          ? 'text-red-400 hover:text-red-300'
                          : 'text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-red-400'
                      }`}
                      title={confirmDeleteId === doc.id ? 'Click again to confirm' : 'Delete document'}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )
                )}
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

      {previewDocId && token && (
        <DocumentPreviewModal
          documentId={previewDocId}
          token={token}
          onClose={() => setPreviewDocId(null)}
        />
      )}
    </div>
  )
}
