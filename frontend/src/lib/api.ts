export async function streamChat(
  message: string,
  threadId: string | null,
  token: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onThreadId?: (threadId: string) => void,
  useDocuments: boolean = false,
) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, thread_id: threadId, use_documents: useDocuments }),
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
            if (data.done) {
              onDone()
              return
            }
            if (data.content) onChunk(data.content)
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
}

export interface DocumentListResponse {
  documents: DocumentStatus[]
}

export async function uploadDocument(
  file: File,
  token: string,
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch('/api/documents/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`)
  }

  return response.json()
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
