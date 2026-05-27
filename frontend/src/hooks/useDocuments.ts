import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import {
  uploadDocument as apiUpload,
  getDocuments as apiGetDocuments,
  getDocumentStatus,
  DuplicateError,
  type DocumentStatus,
} from '@/lib/api'

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentStatus[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)
  const [uploadFailure, setUploadFailure] = useState<{ filename: string; error: string } | null>(null)
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
    setUploadFailure(null)
    try {
      const res = await apiUpload(file, session.access_token, useOcr)
      
      // Query completed status to confirm it didn't fail processing in the backend
      const statusRes = await getDocumentStatus(res.id, session.access_token)
      if (statusRes.status === 'failed') {
        throw new Error(statusRes.error_message || 'Processing failed')
      }

      setDocuments((prev) => [{ ...statusRes, error_message: undefined }, ...prev])
    } catch (err: any) {
      if (err instanceof DuplicateError) {
        setDuplicateWarning(err.message)
      } else {
        console.error('Upload failed:', err)
        setUploadFailure({
          filename: file.name,
          error: err.message || 'Processing or network upload failed',
        })
      }
    } finally {
      setIsUploading(false)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  return {
    documents: documents.filter((d) => d.status !== 'failed'),
    uploadDocument,
    fetchDocuments,
    isUploading,
    hasProcessed,
    duplicateWarning,
    clearDuplicateWarning: () => setDuplicateWarning(null),
    uploadFailure,
    clearUploadFailure: () => setUploadFailure(null),
  }
}
