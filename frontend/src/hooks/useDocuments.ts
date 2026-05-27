import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import {
  uploadDocument as apiUpload,
  getDocuments as apiGetDocuments,
  DuplicateError,
  type DocumentStatus,
} from '@/lib/api'

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentStatus[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)
  const { session } = useAuth()

  const hasProcessed = documents.some((d) => d.status === 'processed')

  const fetchDocuments = useCallback(async () => {
    if (!session?.access_token) return
    try {
      const res = await apiGetDocuments(session.access_token)
      setDocuments(res.documents)
    } catch (err) {
      console.error('Failed to fetch documents:', err)
    }
  }, [session?.access_token])

  const uploadDocument = async (file: File, useOcr: boolean = false) => {
    if (!session?.access_token) return
    setIsUploading(true)
    setDuplicateWarning(null)
    try {
      const res = await apiUpload(file, session.access_token, useOcr)
      setDocuments((prev) => [{ ...res, error_message: undefined }, ...prev])
    } catch (err) {
      if (err instanceof DuplicateError) {
        setDuplicateWarning(err.message)
      } else {
        console.error('Upload failed:', err)
      }
    } finally {
      setIsUploading(false)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  return { documents, uploadDocument, fetchDocuments, isUploading, hasProcessed, duplicateWarning, clearDuplicateWarning: () => setDuplicateWarning(null) }
}
