import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import {
  uploadDocument as apiUpload,
  getDocuments as apiGetDocuments,
  getDocumentStatus,
  deleteDocument as apiDeleteDocument,
  DuplicateError,
  isTransientStatusError,
  type DocumentStatus,
  type PdfParserMode,
} from '@/lib/api'
import * as uploadStorage from '@/lib/uploadStorage'

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

const POLL_TIMEOUT_MS = 5 * 60 * 1000
const POLL_INTERVAL_MS = 2000
const MAX_TRANSIENT_POLL_INTERVAL_MS = 30000
const STATUS_RETRY_MESSAGE = 'Status temporarily unavailable; retrying.'
const STILL_PROCESSING_MESSAGE = 'Still processing. Refresh the document list later for the latest status.'

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

        // Persist polling document ID to localStorage for recovery
        if (session?.user?.id) {
          uploadStorage.addPollingDocument(session.user.id, {
            documentId: res.id,
            filename: res.filename,
            addedAt: Date.now(),
          })
        }

        let lastStatus = res.status
        let latestStatus: DocumentStatus | null = null
        let pollIntervalMs = POLL_INTERVAL_MS
        let transientFailures = 0
        const pollDeadline = Date.now() + POLL_TIMEOUT_MS

        while (Date.now() < pollDeadline) {
          const waitMs = Math.min(pollIntervalMs, Math.max(0, pollDeadline - Date.now()))
          if (waitMs > 0) {
            await new Promise((r) => setTimeout(r, waitMs))
          }

          try {
            const statusRes = await getDocumentStatus(res.id, accessToken)
            latestStatus = statusRes
            lastStatus = statusRes.status
            transientFailures = 0
            pollIntervalMs = POLL_INTERVAL_MS

            setDocuments((prev) =>
              prev.map((doc) =>
                doc.id === res.id
                  ? { ...statusRes, error_message: statusRes.error_message }
                  : doc,
              ),
            )

            if (statusRes.status === 'processed' || statusRes.status === 'failed') {
              break
            }
          } catch (err: unknown) {
            if (!isTransientStatusError(err)) {
              throw err
            }

            transientFailures += 1
            pollIntervalMs = Math.min(
              POLL_INTERVAL_MS * 2 ** Math.min(transientFailures, 4),
              MAX_TRANSIENT_POLL_INTERVAL_MS,
            )
            setDocuments((prev) =>
              prev.map((doc) =>
                doc.id === res.id
                  ? {
                    ...doc,
                    status: doc.status === 'pending' ? 'processing' : doc.status,
                    error_message: STATUS_RETRY_MESSAGE,
                  }
                  : doc,
              ),
            )
          }
        }

        // Clean up polling document from localStorage
        if (session?.user?.id) {
          uploadStorage.removePollingDocument(session.user.id, res.id)
        }

        if (lastStatus === 'failed') {
          failures.push({ filename: file.name, error: latestStatus?.error_message || 'Processing failed' })
        } else if (lastStatus !== 'processed') {
          setDocuments((prev) =>
            prev.map((doc) =>
              doc.id === res.id
                ? {
                  ...doc,
                  status: doc.status === 'pending' ? 'processing' : doc.status,
                  error_message: STILL_PROCESSING_MESSAGE,
                }
                : doc,
            ),
          )
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

  const deleteDocuments = async (ids: string[]): Promise<{ deleted: number; errors: string[] }> => {
    if (!accessToken) throw new Error('Not authenticated')
    const errors: string[] = []
    let deleted = 0
    for (const id of ids) {
      try {
        await apiDeleteDocument(id, accessToken)
        deleted++
      } catch (err: unknown) {
        errors.push(errorMessage(err, `Failed to delete ${id}`))
      }
    }
    setDocuments((prev) => prev.filter((d) => !ids.includes(d.id)))
    return { deleted, errors }
  }

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(async () => {
      await fetchDocuments()
      if (cancelled || !accessToken || !session?.user?.id) return

      // Recover polling for documents tracked in localStorage
      const pollingDocs = uploadStorage.getPollingDocuments(session.user.id)
      if (pollingDocs.length === 0) return

      for (const doc of pollingDocs) {
        // Start a polling loop for each non-terminal document
        const pollLoop = async () => {
          const RECOVER_POLL_TIMEOUT = 10 * 60 * 1000 // 10 minutes
          const deadline = Date.now() + RECOVER_POLL_TIMEOUT

          while (Date.now() < deadline && !cancelled) {
            await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
            if (cancelled) break

            try {
              const statusRes = await getDocumentStatus(doc.documentId, accessToken)
              setDocuments((prev) =>
                prev.map((d) =>
                  d.id === doc.documentId
                    ? { ...statusRes, error_message: statusRes.error_message }
                    : d,
                ),
              )

              if (statusRes.status === 'processed' || statusRes.status === 'failed') {
                uploadStorage.removePollingDocument(session.user.id!, doc.documentId)
                break
              }
            } catch (err: unknown) {
              if (!isTransientStatusError(err)) break
              // Transient — keep polling
            }
          }

          // Timed out — remove from tracking
          if (!cancelled) {
            uploadStorage.removePollingDocument(session.user.id!, doc.documentId)
          }
        }

        void pollLoop()
      }
    }, 0)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [fetchDocuments, accessToken, session?.user?.id])

  /**
   * Add a document (already uploaded via chunked upload) to the list
   * and start polling for its processing status.
   */
  const addDocumentForPolling = useCallback(
    async (documentId: string, filename: string) => {
      if (!accessToken || !session?.user?.id) return

      // Add to document list
      setDocuments((prev) => [
        { id: documentId, filename, status: 'pending' },
        ...prev.filter((d) => d.id !== documentId),
      ])

      // Persist to localStorage
      uploadStorage.addPollingDocument(session.user.id, {
        documentId,
        filename,
        addedAt: Date.now(),
      })

      // Start polling
      const deadline = Date.now() + POLL_TIMEOUT_MS

      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))

        try {
          const statusRes = await getDocumentStatus(documentId, accessToken)

          setDocuments((prev) =>
            prev.map((d) =>
              d.id === documentId
                ? { ...statusRes, error_message: statusRes.error_message }
                : d,
            ),
          )

          if (statusRes.status === 'processed' || statusRes.status === 'failed') {
            break
          }
        } catch (err: unknown) {
          if (!isTransientStatusError(err)) break
        }
      }

      uploadStorage.removePollingDocument(session.user.id, documentId)
    },
    [accessToken, session?.user?.id],
  )

  return {
    documents,
    uploadDocument,
    deleteDocument,
    deleteDocuments,
    fetchDocuments,
    addDocumentForPolling,
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
