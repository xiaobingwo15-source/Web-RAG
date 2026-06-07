import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import {
  uploadDocument as apiUpload,
  getDocuments as apiGetDocuments,
  getDocumentStatus,
  deleteDocument as apiDeleteDocument,
  DuplicateError,
  type DocumentStatus,
  type PdfParserMode,
} from '@/lib/api'

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentStatus[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)
  const [uploadFailure, setUploadFailure] = useState<{ filename: string; error: string } | null>(null)
  const { session } = useAuth()
  const accessToken = session?.access_token

  const hasProcessed = documents.some((d) => d.status === 'processed')

  const fetchDocuments = useCallback(async () => {
    if (!accessToken) return
    setIsLoading(true)
    setLoadError(null)
    try {
      const res = await apiGetDocuments(accessToken)
      setDocuments(res.documents)
    } catch (err: unknown) {
      console.error('Failed to fetch documents:', err)
      setLoadError(errorMessage(err, 'Failed to load documents'))
    } finally {
      setIsLoading(false)
    }
  }, [accessToken])

  const uploadDocument = async (
    fileOrFiles: File | File[],
    useOcr: boolean = false,
    pdfParserMode: PdfParserMode = 'auto',
  ) => {
    if (!accessToken) return
    const files = Array.isArray(fileOrFiles) ? fileOrFiles : [fileOrFiles]
    if (files.length === 0) return

    setIsUploading(true)
    setDuplicateWarning(null)
    setUploadFailure(null)

    const failures: { filename: string; error: string }[] = []

    for (const file of files) {
      try {
        const res = await apiUpload(file, accessToken, useOcr, pdfParserMode)

        // Upload returns immediately with "pending" status.
        // Add to list right away so user sees it processing.
        setDocuments((prev) => [
          { id: res.id, filename: res.filename, status: res.status },
          ...prev.filter((doc) => doc.id !== res.id),
        ])

        // Poll for processing completion (up to 5 minutes)
        const MAX_POLL_ATTEMPTS = 150
        const POLL_INTERVAL_MS = 2000
        let lastStatus = res.status

        for (let i = 0; i < MAX_POLL_ATTEMPTS; i++) {
          await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))

          const statusRes = await getDocumentStatus(res.id, accessToken)
          lastStatus = statusRes.status

          // Update the document in the list with latest status
          setDocuments((prev) =>
            prev.map((doc) =>
              doc.id === res.id
                ? { ...statusRes, error_message: statusRes.error_message }
                : doc,
            ),
          )

          // Terminal states — stop polling
          if (statusRes.status === 'processed' || statusRes.status === 'failed') {
            break
          }
        }

        if (lastStatus === 'failed') {
          const statusRes = await getDocumentStatus(res.id, accessToken)
          failures.push({ filename: file.name, error: statusRes.error_message || 'Processing failed' })
        }
      } catch (err: unknown) {
        if (err instanceof DuplicateError) {
          setDuplicateWarning(err.message)
        } else {
          console.error('Upload failed:', err)
          failures.push({
            filename: file.name,
            error: errorMessage(err, 'Processing or network upload failed'),
          })
        }
      }
    }

    if (failures.length > 0) {
      setUploadFailure(
        failures.length === 1
          ? failures[0]
          : { filename: `${failures.length} files`, error: failures.map((f) => `${f.filename}: ${f.error}`).join('; ') }
      )
    }

    setIsUploading(false)
  }

  const deleteDocument = async (documentId: string): Promise<{ message: string; filename: string }> => {
    if (!accessToken) throw new Error('Not authenticated')
    const result = await apiDeleteDocument(documentId, accessToken)
    setDocuments((prev) => prev.filter((d) => d.id !== documentId))
    return result
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchDocuments()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [fetchDocuments])

  return {
    documents,
    uploadDocument,
    deleteDocument,
    fetchDocuments,
    isUploading,
    isLoading,
    loadError,
    hasProcessed,
    duplicateWarning,
    clearDuplicateWarning: () => setDuplicateWarning(null),
    uploadFailure,
    clearUploadFailure: () => setUploadFailure(null),
  }
}
