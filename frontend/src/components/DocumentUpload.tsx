import { useRef, useState, useEffect, type DragEvent } from 'react'
import { Upload, FileText, CheckCircle, XCircle, Loader2, AlertTriangle, Trash2, Eye, RotateCcw, X, SquareCheck, Square } from 'lucide-react'
import type { DocumentStatus, PdfParserMode, DocumentUploadResponse } from '@/lib/api'
import type { ChunkedUploadProgress, PendingResume } from '@/hooks/useChunkedUpload'
import { DocumentPreviewModal } from './DocumentPreviewModal'
import { ConfirmDialog } from './ConfirmDialog'

const ACCEPTED_TYPES = ['.pdf', '.md', '.txt', '.csv', '.xlsx', '.xls']
const PDF_PARSER_OPTIONS: { value: PdfParserMode; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'pypdfium', label: 'Fast text' },
  { value: 'unstructured', label: 'Layout tables' },
  { value: 'mineru', label: 'MinerU' },
  { value: 'ocr', label: 'OCR' },
]

/** Files above this size use chunked upload */
const CHUNKED_THRESHOLD = 2 * 1024 * 1024 // 2 MB

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function DocumentUpload({
  documents,
  isUploading,
  onUpload,
  onDelete,
  onDeleteMany,
  duplicateWarning,
  onDismissWarning,
  uploadFailure,
  onDismissFailure,
  loadError,
  token,
  chunkedUpload,
  activeUploads = [],
  pendingResumes = [],
  onResumeUpload,
  onCancelUpload,
  onDismissResume,
  onUploadComplete,
}: {
  documents: DocumentStatus[]
  isUploading: boolean
  onUpload: (files: File[], useOcr?: boolean, pdfParserMode?: PdfParserMode) => void
  onDelete?: (documentId: string) => Promise<{ message: string; filename: string }>
  onDeleteMany?: (ids: string[]) => Promise<{ deleted: number; errors: string[] }>
  duplicateWarning?: string | null
  onDismissWarning?: () => void
  uploadFailure?: { filename: string; error: string } | null
  onDismissFailure?: () => void
  loadError?: string | null
  token?: string
  chunkedUpload?: (file: File, useOcr?: boolean, pdfParserMode?: PdfParserMode) => Promise<DocumentUploadResponse>
  activeUploads?: ChunkedUploadProgress[]
  pendingResumes?: PendingResume[]
  onResumeUpload?: (file: File, pending: PendingResume) => Promise<DocumentUploadResponse | false>
  onCancelUpload?: (sessionId: string) => void
  onDismissResume?: (sessionId: string) => void
  onUploadComplete?: (documentId: string, filename: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [useOcr, setUseOcr] = useState(false)
  const [pdfParserMode, setPdfParserMode] = useState<PdfParserMode>('auto')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [previewDocId, setPreviewDocId] = useState<string | null>(null)
  const [chunkedError, setChunkedError] = useState<string | null>(null)

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [isSelecting, setIsSelecting] = useState(false)

  // Confirm dialog state
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean
    title: string
    message: string
    ids: string[]
  }>({ open: false, title: '', message: '', ids: [] })

  const handleDeleteClick = (docId: string) => {
    if (!onDelete) return
    const doc = documents.find((d) => d.id === docId)
    setDeleteError(null)
    setConfirmDialog({
      open: true,
      title: 'Delete Document',
      message: `Are you sure you want to delete "${doc?.metadata?.title || doc?.filename || 'this document'}"? This action cannot be undone.`,
      ids: [docId],
    })
  }

  const handleBulkDelete = () => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) return
    setDeleteError(null)
    setConfirmDialog({
      open: true,
      title: `Delete ${ids.length} Document${ids.length > 1 ? 's' : ''}`,
      message: `Are you sure you want to delete ${ids.length} selected document${ids.length > 1 ? 's' : ''}? This action cannot be undone.`,
      ids,
    })
  }

  const executeDelete = async () => {
    const ids = confirmDialog.ids
    setConfirmDialog({ open: false, title: '', message: '', ids: [] })

    if (ids.length === 1 && onDelete) {
      setDeletingId(ids[0])
      setDeleteError(null)
      try {
        await onDelete(ids[0])
      } catch (err: unknown) {
        setDeleteError(errorMessage(err, 'Failed to delete document'))
      } finally {
        setDeletingId(null)
      }
    } else if (ids.length > 1 && onDeleteMany) {
      setDeletingId('bulk')
      setDeleteError(null)
      try {
        const result = await onDeleteMany(ids)
        if (result.errors.length > 0) {
          setDeleteError(`Deleted ${result.deleted}/${ids.length}. ${result.errors[0]}`)
        }
      } catch (err: unknown) {
        setDeleteError(errorMessage(err, 'Failed to delete documents'))
      } finally {
        setDeletingId(null)
      }
    }

    setSelectedIds(new Set())
    if (selectedIds.size === ids.length) setIsSelecting(false)
  }

  const toggleSelect = (docId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === documents.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(documents.map((d) => d.id)))
    }
  }

  const exitSelectionMode = () => {
    setIsSelecting(false)
    setSelectedIds(new Set())
  }

  const processFiles = async (files: File[]) => {
    setChunkedError(null)

    // Split into chunked vs regular files
    const chunkedFiles: File[] = []
    const regularFiles: File[] = []

    for (const file of files) {
      if (chunkedUpload && file.size > CHUNKED_THRESHOLD) {
        chunkedFiles.push(file)
      } else {
        regularFiles.push(file)
      }
    }

    // Regular upload for small files
    if (regularFiles.length > 0) {
      onUpload(regularFiles, useOcr, pdfParserMode)
    }

    // Chunked upload for large files
    for (const file of chunkedFiles) {
      try {
        const result = await chunkedUpload!(file, useOcr, pdfParserMode)
        onUploadComplete?.(result.id, result.filename)
      } catch (err: unknown) {
        const msg = errorMessage(err, 'Upload failed')
        setChunkedError(`Failed to upload ${file.name}: ${msg}`)
      }
    }
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) void processFiles(files)
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) void processFiles(files)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleResume = async (pending: PendingResume) => {
    // Trigger file picker for resume — the user must re-select the file
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = ACCEPTED_TYPES.join(',')
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      const result = await onResumeUpload?.(file, pending)
      if (!result) {
        setChunkedError(`File doesn't match. Please select "${pending.filename}" (${(pending.totalSize / 1024 / 1024).toFixed(1)} MB)`)
        return
      }
      onUploadComplete?.(result.id, result.filename)
    }
    input.click()
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

  const isAnyUploading = isUploading || activeUploads.some((u) => u.status === 'uploading' || u.status === 'completing')

  return (
    <div className="flex flex-col gap-4">
      {/* Active chunked upload progress bars */}
      {activeUploads.map((upload) => (
        <div
          key={upload.sessionId}
          className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              {upload.status === 'completing' ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-500" />
              ) : upload.status === 'completed' ? (
                <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
              ) : upload.status === 'failed' ? (
                <XCircle className="h-4 w-4 shrink-0 text-red-500" />
              ) : (
                <Upload className="h-4 w-4 shrink-0 text-blue-500" />
              )}
              <span className="truncate text-xs font-medium text-blue-700">
                {upload.filename}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-blue-600">
                {upload.status === 'completing'
                  ? 'Finalizing...'
                  : upload.status === 'completed'
                    ? 'Done'
                    : upload.status === 'failed'
                      ? 'Failed'
                      : `${upload.uploadedChunks}/${upload.totalChunks} chunks`}
              </span>
              {upload.status === 'uploading' && onCancelUpload && (
                <button
                  onClick={() => onCancelUpload(upload.sessionId)}
                  className="text-blue-400 hover:text-red-500 transition-colors"
                  title="Cancel upload"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
          {/* Progress bar */}
          {(upload.status === 'uploading' || upload.status === 'completing') && (
            <div className="mt-1.5 h-1.5 w-full rounded-full bg-blue-100">
              <div
                className="h-full rounded-full bg-blue-500 transition-all duration-300"
                style={{ width: `${upload.percentage}%` }}
              />
            </div>
          )}
          {/* Error */}
          {upload.status === 'failed' && upload.error && (
            <p className="mt-1 text-xs text-red-500">{upload.error}</p>
          )}
        </div>
      ))}

      {/* Resume banners for incomplete sessions */}
      {pendingResumes.map((pending) => (
        <div
          key={pending.sessionId}
          className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2"
        >
          <RotateCcw className="h-4 w-4 shrink-0 text-amber-500" />
          <div className="flex-1 min-w-0">
            <p className="text-xs text-amber-700">
              Upload of <span className="font-semibold">{pending.filename}</span> incomplete
              ({pending.uploadedChunks}/{pending.totalChunks} chunks)
            </p>
          </div>
          <button
            onClick={() => handleResume(pending)}
            className="shrink-0 rounded bg-amber-500 px-2 py-0.5 text-xs font-medium text-white hover:bg-amber-600 transition-colors"
          >
            Resume
          </button>
          {onDismissResume && (
            <button
              onClick={() => onDismissResume(pending.sessionId)}
              className="text-amber-400 hover:text-amber-600 transition-colors"
              title="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      ))}

      {/* Chunked upload error */}
      {chunkedError && (
        <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <div className="flex-1">
            <p className="text-xs text-red-600">{chunkedError}</p>
          </div>
          <button onClick={() => setChunkedError(null)} className="text-red-400 hover:text-red-600">
            <XCircle className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Existing error banners */}
      {uploadFailure && (
        <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <div className="flex-1">
            <h5 className="text-xs font-bold text-red-700">Upload Failed</h5>
            <p className="text-xs text-red-600 mt-0.5">
              Failed to process <span className="font-semibold">{uploadFailure.filename}</span>: {uploadFailure.error}
            </p>
          </div>
          {onDismissFailure && (
            <button onClick={onDismissFailure} className="text-red-400 hover:text-red-600">
              <XCircle className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {duplicateWarning && (
        <div className="flex items-start gap-2 rounded-md border border-yellow-300 bg-yellow-50 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-500" />
          <div className="flex-1">
            <p className="text-sm text-yellow-700">{duplicateWarning}</p>
          </div>
          {onDismissWarning && (
            <button onClick={onDismissWarning} className="text-yellow-400 hover:text-yellow-600">
              <XCircle className="h-4 w-4" />
            </button>
          )}
        </div>
      )}

      {deleteError && (
        <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <div className="flex-1">
            <p className="text-xs text-red-600">{deleteError}</p>
          </div>
          <button onClick={() => setDeleteError(null)} className="text-red-400 hover:text-red-600">
            <XCircle className="h-4 w-4" />
          </button>
        </div>
      )}

      {loadError && (
        <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
          <div className="flex-1">
            <h5 className="text-xs font-bold text-red-700">Documents Unavailable</h5>
            <p className="mt-0.5 text-xs text-red-600">{loadError}</p>
          </div>
        </div>
      )}

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => inputRef.current?.click()}
        className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed border-border p-6 text-center transition-colors hover:border-primary/50"
      >
        {isAnyUploading ? (
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        ) : (
          <Upload className="h-8 w-8 text-muted-foreground" />
        )}
        <p className="text-sm text-muted-foreground">
          {isAnyUploading ? 'Uploading...' : 'Drop documents here or click to browse'}
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
        <label
          className="flex items-center gap-2 text-xs text-muted-foreground"
          onClick={(e) => e.stopPropagation()}
        >
          PDF parser
          <select
            value={pdfParserMode}
            onChange={(e) => setPdfParserMode(e.target.value as PdfParserMode)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
          >
            {PDF_PARSER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES.join(',')}
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {/* Document list */}
      {documents.length > 0 && (
        <div className="space-y-2">
          {/* Header with select controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {(onDelete || onDeleteMany) && (
                <button
                  onClick={() => {
                    if (isSelecting) {
                      exitSelectionMode()
                    } else {
                      setIsSelecting(true)
                    }
                  }}
                  className={`text-xs px-2 py-1 rounded-md border transition-colors cursor-pointer ${
                    isSelecting
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:text-foreground hover:bg-muted'
                  }`}
                >
                  {isSelecting ? 'Cancel' : 'Select'}
                </button>
              )}
              <h4 className="text-sm font-medium text-foreground">Uploaded Documents</h4>
            </div>
            {isSelecting && selectedIds.size > 0 && (
              <button
                onClick={handleBulkDelete}
                disabled={deletingId === 'bulk'}
                className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md bg-red-500 text-white hover:bg-red-600 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {deletingId === 'bulk' ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Trash2 className="h-3 w-3" />
                )}
                Delete ({selectedIds.size})
              </button>
            )}
          </div>

          {/* Select all row */}
          {isSelecting && (
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              {selectedIds.size === documents.length ? (
                <SquareCheck className="h-4 w-4 text-primary" />
              ) : (
                <Square className="h-4 w-4" />
              )}
              {selectedIds.size === documents.length ? 'Deselect all' : 'Select all'}
            </button>
          )}

          {documents.map((doc) => (
            <div
              key={doc.id}
              className={`group rounded-md border px-3 py-2 transition-colors ${
                selectedIds.has(doc.id) ? 'border-primary/50 bg-primary/5' : 'border-border'
              }`}
            >
              <div className="flex items-center gap-2">
                {/* Checkbox */}
                {isSelecting && (
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleSelect(doc.id) }}
                    className="shrink-0 cursor-pointer"
                  >
                    {selectedIds.has(doc.id) ? (
                      <SquareCheck className="h-4 w-4 text-primary" />
                    ) : (
                      <Square className="h-4 w-4 text-muted-foreground" />
                    )}
                  </button>
                )}
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
                {onDelete && !isSelecting && (
                  deletingId === doc.id ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteClick(doc.id) }}
                      className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-red-400 transition-colors"
                      title="Delete document"
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
              {doc.status === 'failed' && doc.error_message && (
                <p className="mt-1.5 text-xs text-red-300">
                  {doc.error_message}
                </p>
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

      <ConfirmDialog
        open={confirmDialog.open}
        title={confirmDialog.title}
        message={confirmDialog.message}
        confirmLabel={confirmDialog.ids.length > 1 ? `Delete ${confirmDialog.ids.length} Documents` : 'Delete'}
        danger
        onConfirm={executeDelete}
        onCancel={() => setConfirmDialog({ open: false, title: '', message: '', ids: [] })}
      />
    </div>
  )
}
