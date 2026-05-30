export interface StreamError extends Error {
  error_code?: string
}

export interface ActionMeta {
  type: string
  source: string
  data: Record<string, unknown>
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
  images?: string[],
  onThought?: (thought: string, action?: ActionMeta) => void,
) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120_000)

  let response: Response
  try {
    response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        thread_id: threadId,
        use_documents: useDocuments,
        retrieval_mode: retrievalMode,
        ...(images && images.length > 0 ? { images } : {}),
      }),
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timeout)
    const isAbort = (err as Error).name === 'AbortError'
    onError(new Error(isAbort ? 'Request timed out' : (err as Error).message))
    return
  }

  if (!response.ok) {
    clearTimeout(timeout)
    onError(new Error(`HTTP ${response.status}`))
    return
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) {
    onDone()
    return
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n').map(l => l.trimEnd())
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.thread_id && onThreadId) onThreadId(data.thread_id)
            if (data.type === 'error') {
              const err: StreamError = new Error(data.content)
              err.error_code = data.error_code
              clearTimeout(timeout)
              onError(err)
              return
            } else if (data.type === 'thought' && onThought) {
              if (data.action_type) {
                onThought(data.content, {
                  type: data.action_type,
                  source: data.action_source,
                  data: data.action_data || {},
                })
              } else {
                onThought(data.content)
              }
            } else if (data.done || data.type === 'done') {
              clearTimeout(timeout)
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
    clearTimeout(timeout)
    onDone()
  } catch (err) {
    clearTimeout(timeout)
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
  const response = await fetch('/api/documents', {
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

export async function deleteDocument(
  documentId: string,
  token: string,
): Promise<{ message: string; filename: string }> {
  const response = await fetch(`/api/documents/${documentId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Delete document failed: ${response.status}`)
  return response.json()
}

export interface DocumentChunksResponse {
  document_id: string
  filename: string
  metadata?: {
    title?: string
    summary?: string
    tags?: string[]
    language?: string
  }
  chunk_count: number
  full_text: string
}

export async function fetchDocumentChunks(
  documentId: string,
  token: string,
): Promise<DocumentChunksResponse> {
  const response = await fetch(`/api/documents/${documentId}/chunks`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch chunks failed: ${response.status}`)
  return response.json()
}


// --- Admin API ---

export interface AdminThread {
  id: string
  title: string
  created_at: string
  message_count: number
}

export interface AdminClient {
  email: string
  user_id: string
  threads: AdminThread[]
}

export interface AdminConversationsResponse {
  clients: AdminClient[]
}

export interface AdminMessage {
  id: string
  thread_id: string
  user_id: string
  role: string
  content: string
  created_at: string
}

export interface AdminMessagesResponse {
  messages: AdminMessage[]
}

export async function getAdminConversations(token: string): Promise<AdminConversationsResponse> {
  const response = await fetch('/api/admin/conversations', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch admin conversations failed: ${response.status}`)
  return response.json()
}

export async function getAdminThreadMessages(
  threadId: string,
  token: string,
): Promise<AdminMessagesResponse> {
  const response = await fetch(`/api/admin/conversations/${threadId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch admin messages failed: ${response.status}`)
  return response.json()
}

export interface UserProfileResponse {
  id: string
  email: string
  role: string
  tenant_id?: string | null
  status?: string
}

export async function getUserProfile(token: string): Promise<UserProfileResponse> {
  const response = await fetch('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch profile failed: ${response.status}`)
  return response.json()
}

export interface SystemSettings {
  GOOGLE_API_KEY?: string
  OPENROUTER_API_KEY?: string
  TAVLY_API_KEY?: string
  LANGFUSE_PUBLIC_KEY?: string
  LANGFUSE_SECRET_KEY?: string
  LANGFUSE_BASE_URL?: string
}

export async function getAdminSettings(token: string): Promise<SystemSettings> {
  const response = await fetch('/api/admin/settings', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch admin settings failed: ${response.status}`)
  return response.json()
}

export async function saveAdminSettings(settings: SystemSettings, token: string): Promise<void> {
  const response = await fetch('/api/admin/settings', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(settings),
  })
  if (!response.ok) throw new Error(`Save admin settings failed: ${response.status}`)
}


// --- Admin Manual Answer API ---

export interface FlaggedMessage {
  message_id: string
  thread_id: string
  thread_title: string
  client_email: string
  client_user_id: string
  content: string
  created_at: string
  has_admin_response: boolean
}

export interface FlaggedMessagesResponse {
  flagged: FlaggedMessage[]
}

export interface FlaggedCountResponse {
  count: number
}

export interface AdminRespondResponse {
  status: string
  message_id: string
}

export async function getFlaggedMessages(token: string): Promise<FlaggedMessagesResponse> {
  const response = await fetch('/api/admin/flagged', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch flagged messages failed: ${response.status}`)
  return response.json()
}

export async function getFlaggedCount(token: string): Promise<FlaggedCountResponse> {
  const response = await fetch('/api/admin/flagged/count', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch flagged count failed: ${response.status}`)
  return response.json()
}

export async function submitAdminResponse(
  threadId: string,
  content: string,
  token: string,
): Promise<AdminRespondResponse> {
  const response = await fetch(`/api/admin/conversations/${threadId}/respond`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) throw new Error(`Submit admin response failed: ${response.status}`)
  return response.json()
}


// --- Admin User Management API ---

export interface AdminUser {
  id: string
  email: string
  role: string
  status: string
  created_at: string
}

export interface AdminUsersResponse {
  users: AdminUser[]
}

export async function getAdminUsers(token: string): Promise<AdminUsersResponse> {
  const response = await fetch('/api/admin/users', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch admin users failed: ${response.status}`)
  return response.json()
}

export async function updateUserStatus(
  userId: string,
  action: 'approve' | 'suspend',
  token: string,
): Promise<{ status: string }> {
  const response = await fetch(`/api/admin/users/${userId}/${action}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Update user status failed: ${response.status}`)
  return response.json()
}


// --- Tenant Validation ---

export interface TenantInfo {
  id: string
  name: string
  slug: string
}

export async function validateTenantSlug(slug: string): Promise<TenantInfo> {
  const response = await fetch(`/api/auth/tenant/${encodeURIComponent(slug)}`)
  if (!response.ok) throw new Error(`Invalid tenant: ${response.status}`)
  return response.json()
}

export async function resolveTenant(): Promise<TenantInfo> {
  const response = await fetch('/api/auth/tenant/resolve')
  if (!response.ok) throw new Error(`Could not resolve tenant: ${response.status}`)
  return response.json()
}
