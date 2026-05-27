export interface StreamError extends Error {
  error_code?: string
}

export async function streamChat(
  message: string,
  threadId: string | null,
  token: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: StreamError) => void,
  onThreadId?: (threadId: string) => void,
  useDocuments: boolean = false,
  retrievalMode: string = 'hybrid',
  onThought?: (thought: string) => void,
) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, thread_id: threadId, use_documents: useDocuments, retrieval_mode: retrievalMode }),
  })

  if (!response.ok) {
    onError(new Error(`HTTP ${response.status}`))
    return
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) return

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n')
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.thread_id && onThreadId) onThreadId(data.thread_id)
            if (data.type === 'error') {
              const err: StreamError = new Error(data.content)
              err.error_code = data.error_code
              onError(err)
              return
            } else if (data.type === 'thought' && onThought) {
              onThought(data.content)
            } else if (data.done || data.type === 'done') {
              onDone()
              return
            } else if (data.content) {
              onChunk(data.content)
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }
    }
    onDone()
  } catch (err) {
    onError(err as Error)
  }
}

export interface ThreadSummary {
  id: string
  title: string
  created_at: string
}

export interface MessageResponse {
  id: string
  role: string
  content: string
  created_at: string
}

export async function getThreads(token: string): Promise<ThreadSummary[]> {
  const response = await fetch('/api/chat/threads', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch threads failed: ${response.status}`)
  const data = await response.json()
  return data.threads
}

export async function getThreadMessages(
  threadId: string,
  token: string,
): Promise<MessageResponse[]> {
  const response = await fetch(`/api/chat/threads/${threadId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch messages failed: ${response.status}`)
  const data = await response.json()
  return data.messages
}

export async function deleteThread(
  threadId: string,
  token: string,
): Promise<void> {
  const response = await fetch(`/api/chat/threads/${threadId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Delete thread failed: ${response.status}`)
}

export interface DocumentUploadResponse {
  id: string
  filename: string
  status: string
}

export interface DocumentStatus {
  id: string
  filename: string
  status: string
  error_message?: string
  metadata?: {
    title?: string
    summary?: string
    tags?: string[]
    language?: string
  }
}

export interface DocumentListResponse {
  documents: DocumentStatus[]
}

export async function uploadDocument(
  file: File,
  token: string,
  useOcr: boolean = false,
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (useOcr) formData.append('use_ocr', 'true')

  const response = await fetch('/api/documents/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })

  if (response.status === 409) {
    const detail = await response.json()
    throw new DuplicateError(detail.detail?.message || 'Document already uploaded', detail.detail?.existing_document_id)
  }

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`)
  }

  return response.json()
}

export class DuplicateError extends Error {
  existingDocumentId?: string
  constructor(message: string, existingDocumentId?: string) {
    super(message)
    this.name = 'DuplicateError'
    this.existingDocumentId = existingDocumentId
  }
}

export async function getDocumentStatus(
  documentId: string,
  token: string,
): Promise<DocumentStatus> {
  const response = await fetch(`/api/documents/status/${documentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    throw new Error(`Status check failed: ${response.status}`)
  }

  return response.json()
}

export async function getDocuments(token: string): Promise<DocumentListResponse> {
  const response = await fetch('/api/documents/', {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!response.ok) {
    throw new Error(`Fetch documents failed: ${response.status}`)
  }

  return response.json()
}

export interface DocumentMetadataResponse {
  tags: string[]
  languages: string[]
}

export async function getDocumentMetadata(token: string): Promise<DocumentMetadataResponse> {
  const response = await fetch('/api/documents/metadata', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch metadata failed: ${response.status}`)
  return response.json()
}
