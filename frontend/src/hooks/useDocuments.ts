import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from './useAuth'
import {
  uploadDocument as apiUpload,
  getDocuments as apiGetDocuments,
  getDocumentStatus as apiGetStatus,
  type DocumentStatus,
} from '@/lib/api'

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentStatus[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const { session } = useAuth()
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const hasProcessed = documents.some((d) => d.status === 'processed')
  const hasPending = documents.some((d) => d.status === 'pending')

  const fetchDocuments = useCallback(async () => {
    if (!session?.access_token) return
    try {
      const res = await apiGetDocuments(session.access_token)
      setDocuments(res.documents)
    } catch (err) {
      console.error('Failed to fetch documents:', err)
    }
  }, [session?.access_token])

  const uploadDocument = async (file: File) => {
    if (!session?.access_token) return
    setIsUploading(true)
    try {
      const res = await apiUpload(file, session.access_token)
      setDocuments((prev) => [{ ...res, error_message: undefined }, ...prev])
    } catch (err) {
      console.error('Upload failed:', err)
    } finally {
      setIsUploading(false)
    }
  }

  // Poll pending documents
  useEffect(() => {
    if (!hasPending || !session?.access_token) {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }

    pollRef.current = setInterval(async () => {
      const pending = documents.filter((d) => d.status === 'pending')
      for (const doc of pending) {
        try {
          const updated = await apiGetStatus(doc.id, session.access_token)
          setDocuments((prev) =>
            prev.map((d) => (d.id === updated.id ? updated : d)),
          )
        } catch (err) {
          console.error('Poll failed:', err)
        }
      }
    }, 3000)

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [hasPending, documents, session?.access_token])

  // Fetch on mount
  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  return { documents, uploadDocument, fetchDocuments, isUploading, hasProcessed }
}
