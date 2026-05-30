import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import {
  uploadDocument as apiUpload,
  getDocuments as apiGetDocuments,
  getDocumentStatus,
  deleteDocument as apiDeleteDocument,
  DuplicateError,
  type DocumentStatus,
} from '@/lib/api'

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentStatus[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)
  const [uploadFailure, setUploadFailure] = useState<{ filename: string; error: string } | null>(null)
  const { session } = useAuth()

  const hasProcessed = documents.some((d) => d.status === 'processed')

  const fetchDocuments = useCallback(async () => {
    if (!session?.access_token) return
    setIsLoading(true)
    setLoadError(null)
    try {
      const res = await apiGetDocuments(session.access_token)
      setDocuments(res.documents)
    } catch (err: any) {
      console.error('Failed to fetch documents:', err)
      setLoadError(err.message || 'Failed to load documents')
    } finally {
      setIsLoading(false)
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
      setDocuments((prev) => [
        { ...statusRes, error_message: statusRes.error_message },
        ...prev.filter((doc) => doc.id !== statusRes.id),
      ])

      if (statusRes.status === 'failed') {
        throw new Error(statusRes.error_message || 'Processing failed')
      }
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

  const deleteDocument = async (documentId: string): Promise<{ message: string; filename: string }> => {
    if (!session?.access_token) throw new Error('Not authenticated')
    const result = await apiDeleteDocument(documentId, session.access_token)
    setDocuments((prev) => prev.filter((d) => d.id !== documentId))
    return result
  }

  useEffect(() => {
    fetchDocuments()
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
