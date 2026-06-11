/**
 * Chunked upload hook — resilient file upload that survives page refreshes.
 *
 * Splits files into 2 MB chunks, uploads via XHR (for progress events),
 * persists session state to localStorage after each confirmed chunk,
 * and supports resuming incomplete uploads when the user re-selects the same file.
 */

import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import {
  initUploadSession,
  completeUploadSession,
  getUploadSessionStatus,
  cancelUploadSession,
  DuplicateError,
  type DocumentUploadResponse,
  type PdfParserMode,
} from '@/lib/api'
import * as uploadStorage from '@/lib/uploadStorage'

const DEFAULT_CHUNK_SIZE = 2 * 1024 * 1024 // 2 MB
const MAX_CHUNK_RETRIES = 3
const RETRY_BASE_DELAY_MS = 1000

export interface ChunkedUploadProgress {
  sessionId: string
  filename: string
  totalChunks: number
  uploadedChunks: number
  percentage: number // 0-100
  status: 'uploading' | 'completing' | 'completed' | 'failed'
  error?: string
}

export interface PendingResume {
  sessionId: string
  filename: string
  totalSize: number
  uploadedChunks: number
  totalChunks: number
}

// --- SHA-256 helper ---

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

// --- XHR upload with progress ---

function xhrUploadChunk(
  url: string,
  token: string,
  formData: FormData,
  onProgress: (loaded: number, total: number) => void,
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total)
    }

    xhr.onload = () => resolve({ status: xhr.status, body: xhr.responseText })
    xhr.onerror = () => reject(new Error('Network error during chunk upload'))
    xhr.onabort = () => reject(new Error('Upload aborted'))
    xhr.ontimeout = () => reject(new Error('Upload timed out'))

    xhr.timeout = 120_000 // 2 min per chunk
    xhr.send(formData)
  })
}

// --- Hook ---

export function useChunkedUpload() {
  const { session } = useAuth()
  const token = session?.access_token
  const userId = session?.user?.id

  const [activeUploads, setActiveUploads] = useState<ChunkedUploadProgress[]>([])
  const [pendingResumes, setPendingResumes] = useState<PendingResume[]>([])

  // Detect incomplete sessions on mount
  useEffect(() => {
    if (!userId) return
    const sessions = uploadStorage.getSessions(userId)
    if (sessions.length === 0) return

    const pending: PendingResume[] = sessions.map((s) => ({
      sessionId: s.sessionId,
      filename: s.filename,
      totalSize: s.totalSize,
      uploadedChunks: s.uploadedChunks,
      totalChunks: s.totalChunks,
    }))
    setPendingResumes(pending)
  }, [userId])

  // beforeunload handler
  useEffect(() => {
    const hasActive = activeUploads.some((u) => u.status === 'uploading')
    if (!hasActive) return

    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [activeUploads])

  const updateProgress = useCallback((sessionId: string, update: Partial<ChunkedUploadProgress>) => {
    setActiveUploads((prev) =>
      prev.map((u) => (u.sessionId === sessionId ? { ...u, ...update } : u)),
    )
  }, [])

  /**
   * Upload a file using chunked upload. Returns the DocumentUploadResponse on success.
   */
  const upload = useCallback(
    async (
      file: File,
      useOcr: boolean = false,
      pdfParserMode: PdfParserMode = 'auto',
    ): Promise<DocumentUploadResponse> => {
      if (!token || !userId) throw new Error('Not authenticated')

      const chunkSize = DEFAULT_CHUNK_SIZE

      // Init session
      const init = await initUploadSession(
        {
          filename: file.name,
          mimeType: file.type || 'application/octet-stream',
          totalSize: file.size,
          chunkSize,
          useOcr,
          pdfParserMode,
        },
        token,
      )

      const sessionId = init.session_id

      // Track progress
      const progress: ChunkedUploadProgress = {
        sessionId,
        filename: file.name,
        totalChunks: init.total_chunks,
        uploadedChunks: 0,
        percentage: 0,
        status: 'uploading',
      }
      setActiveUploads((prev) => [...prev.filter((u) => u.sessionId !== sessionId), progress])

      // Persist to localStorage
      uploadStorage.addSession(userId, {
        sessionId,
        filename: file.name,
        totalSize: file.size,
        totalChunks: init.total_chunks,
        uploadedChunks: 0,
        useOcr,
        pdfParserMode,
        startedAt: Date.now(),
      })

      // Remove from pending resumes if it was there
      setPendingResumes((prev) => prev.filter((r) => r.sessionId !== sessionId))

      try {
        // Upload chunks sequentially
        for (let i = 0; i < init.total_chunks; i++) {
          const start = i * chunkSize
          const end = Math.min(start + chunkSize, file.size)
          const blob = file.slice(start, end)

          // Compute SHA-256
          const buffer = await blob.arrayBuffer()
          const checksum = await sha256Hex(buffer)

          let lastError: Error | null = null
          for (let attempt = 0; attempt < MAX_CHUNK_RETRIES; attempt++) {
            try {
              const formData = new FormData()
              formData.append('file', blob, file.name)
              formData.append('checksum', checksum)

              const res = await xhrUploadChunk(
                `/api/documents/upload/${sessionId}/chunk/${i}`,
                token,
                formData,
                () => {
                  // Per-chunk XHR progress (not reflected in overall %)
                  // Could add a sub-progress bar later
                },
              )

              if (res.status === 422) {
                throw new Error('Chunk checksum mismatch')
              }
              if (res.status === 401) {
                throw new Error('Authentication expired')
              }
              if (res.status === 409) {
                const body = JSON.parse(res.body)
                throw new Error(body.detail || 'Session conflict')
              }
              if (res.status >= 400) {
                throw new Error(`Chunk upload failed (${res.status})`)
              }

              // Success — break retry loop
              lastError = null
              break
            } catch (err) {
              lastError = err instanceof Error ? err : new Error(String(err))
              if (lastError.message === 'Authentication expired') throw lastError

              // Wait before retry
              if (attempt < MAX_CHUNK_RETRIES - 1) {
                await new Promise((r) => setTimeout(r, RETRY_BASE_DELAY_MS * 2 ** attempt))
              }
            }
          }

          if (lastError) {
            throw lastError
          }

          // Update progress
          const uploaded = i + 1
          const pct = Math.round((uploaded / init.total_chunks) * 100)
          updateProgress(sessionId, { uploadedChunks: uploaded, percentage: pct })
          uploadStorage.updateSessionProgress(userId, sessionId, uploaded)
        }

        // All chunks uploaded — complete
        updateProgress(sessionId, { status: 'completing', percentage: 100 })

        const result = await completeUploadSession(sessionId, token)

        updateProgress(sessionId, { status: 'completed' })
        uploadStorage.removeSession(userId, sessionId)

        // Clean up progress after a delay
        setTimeout(() => {
          setActiveUploads((prev) => prev.filter((u) => u.sessionId !== sessionId))
        }, 3000)

        return result
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed'
        updateProgress(sessionId, { status: 'failed', error: message })

        // Keep session in localStorage so user can see the error
        // It will be cleaned up on next page load or manual cancel

        // If it's a duplicate error, re-throw as DuplicateError
        if (message.includes('already uploaded')) {
          throw new DuplicateError(message)
        }

        throw err
      }
    },
    [token, userId, updateProgress],
  )

  /**
   * Cancel an in-progress upload session.
   */
  const cancelUpload = useCallback(
    async (sessionId: string) => {
      if (!token) return
      try {
        await cancelUploadSession(sessionId, token)
      } catch {
        // Non-fatal — clean up locally anyway
      }
      uploadStorage.removeSession(userId!, sessionId)
      setActiveUploads((prev) => prev.filter((u) => u.sessionId !== sessionId))
      setPendingResumes((prev) => prev.filter((r) => r.sessionId !== sessionId))
    },
    [token, userId],
  )

  /**
   * Resume an incomplete upload. The user must re-select the same file.
   * Returns the completed document when resume succeeds, false otherwise.
   */
  const resumeUpload = useCallback(
    async (file: File, pendingResume: PendingResume): Promise<DocumentUploadResponse | false> => {
      if (!token || !userId) return false

      // Verify file identity
      if (file.name !== pendingResume.filename || file.size !== pendingResume.totalSize) {
        return false
      }

      // Check server state
      let serverStatus: { status: string; uploaded_chunks: number; total_chunks: number }
      try {
        serverStatus = await getUploadSessionStatus(pendingResume.sessionId, token)
      } catch {
        // Session expired or not found
        uploadStorage.removeSession(userId, pendingResume.sessionId)
        setPendingResumes((prev) => prev.filter((r) => r.sessionId !== pendingResume.sessionId))
        return false
      }

      if (serverStatus.status !== 'uploading') {
        // Already completed or failed
        uploadStorage.removeSession(userId, pendingResume.sessionId)
        setPendingResumes((prev) => prev.filter((r) => r.sessionId !== pendingResume.sessionId))
        return false
      }

      const startChunk = Math.max(serverStatus.uploaded_chunks, pendingResume.uploadedChunks)
      const sessionId = pendingResume.sessionId
      const chunkSize = DEFAULT_CHUNK_SIZE

      // Resume progress tracking
      const pct = Math.round((startChunk / serverStatus.total_chunks) * 100)
      setActiveUploads((prev) => [
        ...prev.filter((u) => u.sessionId !== sessionId),
        {
          sessionId,
          filename: file.name,
          totalChunks: serverStatus.total_chunks,
          uploadedChunks: startChunk,
          percentage: pct,
          status: 'uploading',
        },
      ])

      setPendingResumes((prev) => prev.filter((r) => r.sessionId !== sessionId))

      try {
        for (let i = startChunk; i < serverStatus.total_chunks; i++) {
          const start = i * chunkSize
          const end = Math.min(start + chunkSize, file.size)
          const blob = file.slice(start, end)
          const buffer = await blob.arrayBuffer()
          const checksum = await sha256Hex(buffer)

          let lastError: Error | null = null
          for (let attempt = 0; attempt < MAX_CHUNK_RETRIES; attempt++) {
            try {
              const formData = new FormData()
              formData.append('file', blob, file.name)
              formData.append('checksum', checksum)

              const res = await xhrUploadChunk(
                `/api/documents/upload/${sessionId}/chunk/${i}`,
                token,
                formData,
                () => {},
              )

              if (res.status >= 400) {
                const body = res.status === 422 ? 'Checksum mismatch' : `HTTP ${res.status}`
                throw new Error(body)
              }
              lastError = null
              break
            } catch (err) {
              lastError = err instanceof Error ? err : new Error(String(err))
              if (attempt < MAX_CHUNK_RETRIES - 1) {
                await new Promise((r) => setTimeout(r, RETRY_BASE_DELAY_MS * 2 ** attempt))
              }
            }
          }
          if (lastError) throw lastError

          const uploaded = i + 1
          updateProgress(sessionId, { uploadedChunks: uploaded, percentage: Math.round((uploaded / serverStatus.total_chunks) * 100) })
          uploadStorage.updateSessionProgress(userId, sessionId, uploaded)
        }

        updateProgress(sessionId, { status: 'completing', percentage: 100 })
        const result = await completeUploadSession(sessionId, token)
        updateProgress(sessionId, { status: 'completed' })
        uploadStorage.removeSession(userId, sessionId)

        setTimeout(() => {
          setActiveUploads((prev) => prev.filter((u) => u.sessionId !== sessionId))
        }, 3000)

        return result
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Resume failed'
        updateProgress(sessionId, { status: 'failed', error: message })
        return false
      }
    },
    [token, userId, updateProgress],
  )

  /**
   * Dismiss a pending resume (user doesn't want to resume).
   */
  const dismissResume = useCallback(
    (sessionId: string) => {
      if (!userId) return
      uploadStorage.removeSession(userId, sessionId)
      setPendingResumes((prev) => prev.filter((r) => r.sessionId !== sessionId))
    },
    [userId],
  )

  return {
    upload,
    activeUploads,
    pendingResumes,
    resumeUpload,
    cancelUpload,
    dismissResume,
  }
}
