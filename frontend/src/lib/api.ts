export interface StreamError extends Error {
  error_code?: string
}

export interface ActionMeta {
  type: string
  source: string
  data: Record<string, unknown>
}

export interface StreamHandle {
  abort: () => void
}

export interface RetrievalSource {
  document_id: string
  filename?: string | null
  chunk_id: string
  score: number
  snippet: string
  retrieval_mode: string
}

export async function streamChat(
  message: string,
  threadId: string | null,
  token: string,
  onChunk: (text: string) => void,
  onDone: (messageId?: string) => void,
  onError: (err: StreamError) => void,
  onThreadId?: (threadId: string) => void,
  useDocuments: boolean = false,
  retrievalMode: string = 'hybrid',
  images?: string[],
  onThought?: (thought: string, action?: ActionMeta) => void,
  onSources?: (sources: RetrievalSource[]) => void,
  replyTo?: string,
): Promise<StreamHandle> {
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
        ...(replyTo ? { reply_to: replyTo } : {}),
      }),
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timeout)
    const isAbort = (err as Error).name === 'AbortError'
    onError(new Error(isAbort ? 'Request timed out' : (err as Error).message))
    return { abort: () => {} }
  }

  if (!response.ok) {
    clearTimeout(timeout)
    onError(new Error(`HTTP ${response.status}`))
    return { abort: () => {} }
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) {
    onDone()
    return { abort: () => {} }
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
              return { abort: () => {} }
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
            } else if (data.type === 'sources' && onSources) {
              onSources(data.sources || [])
            } else if (data.done || data.type === 'done') {
              clearTimeout(timeout)
              onDone(data.message_id)
              return { abort: () => {} }
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
  return { abort: () => controller.abort() }
}

export interface WidgetSessionResponse {
  token: string
  session_id: string
  expires_in: number
}

export async function createWidgetSession(tenantSlug: string): Promise<WidgetSessionResponse> {
  const response = await fetch('/api/widget/session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ tenant_slug: tenantSlug }),
  })
  if (!response.ok) throw new Error(`Create widget session failed: ${response.status}`)
  return response.json()
}

export async function streamWidgetChat(
  message: string,
  threadId: string | null,
  token: string,
  onChunk: (text: string) => void,
  onDone: (messageId?: string) => void,
  onError: (err: StreamError) => void,
  onThreadId?: (threadId: string) => void,
  images?: string[],
): Promise<StreamHandle> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120_000)

  let response: Response
  try {
    response = await fetch('/api/widget/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        thread_id: threadId,
        ...(images && images.length > 0 ? { images } : {}),
      }),
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timeout)
    const isAbort = (err as Error).name === 'AbortError'
    onError(new Error(isAbort ? 'Request timed out' : (err as Error).message))
    return { abort: () => {} }
  }

  if (!response.ok) {
    clearTimeout(timeout)
    onError(new Error(`HTTP ${response.status}`))
    return { abort: () => {} }
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()

  if (!reader) {
    clearTimeout(timeout)
    onDone()
    return { abort: () => {} }
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
              return { abort: () => {} }
            } else if (data.done || data.type === 'done') {
              clearTimeout(timeout)
              onDone(data.message_id)
              return { abort: () => {} }
            } else if (data.type === 'token' && data.content) {
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
  return { abort: () => controller.abort() }
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
  reply_to?: string | null
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
  MODEL_PROVIDER?: 'openrouter' | 'mistral' | string
  GOOGLE_API_KEY?: string
  OPENROUTER_API_KEY?: string
  OPENROUTER_MODEL?: string
  OPENROUTER_FALLBACK_MODEL?: string
  MISTRAL_API_KEY?: string
  MISTRAL_MODEL?: string
  TAVLY_API_KEY?: string
  COHERE_API_KEY?: string
  QDRANT_URL?: string
  QDRANT_API_KEY?: string
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

// --- Admin RAG Evaluation API ---

export interface RagEvalCase {
  id: string
  suite_id?: string | null
  tenant_id: string
  question: string
  expected_facts: string[]
  expected_answer?: string | null
  expected_document_id?: string | null
  tags: string[]
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface RagEvalCaseCreate {
  question: string
  expected_facts: string[]
  expected_answer?: string | null
  expected_document_id?: string | null
  tags?: string[]
  enabled?: boolean
}

export type RagEvalCaseUpdate = Partial<RagEvalCaseCreate>

export interface RagEvalRunSummary {
  id: string
  tenant_id: string
  suite_id?: string | null
  status: string
  retrieval_mode: string
  model_provider?: string | null
  model_name?: string | null
  total_cases: number
  passed_cases: number
  avg_context_relevance_score: number
  avg_groundedness_score: number
  avg_answer_relevance_score: number
  failure_reason?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at: string
}

export interface RagEvalResult {
  id: string
  tenant_id: string
  run_id: string
  case_id?: string | null
  question: string
  expected_facts: string[]
  answer: string
  sources: RetrievalSource[]
  context_relevance_score: number
  groundedness_score: number
  answer_relevance_score: number
  passed: boolean
  failure_reason?: string | null
  created_at: string
}

export interface RagEvalRunDetail {
  run: RagEvalRunSummary
  results: RagEvalResult[]
}

export interface RagQualitySource {
  document_id?: string | null
  filename?: string | null
  chunk_id?: string | null
  score?: number | null
  snippet?: string | null
  content?: string | null
  retrieval_mode?: string | null
}

export interface RagQualityRetrievalLog {
  id: string
  query: string
  retrieval_mode: string
  chunk_count: number
  source_count: number
  top_score?: number | null
  duration_ms?: number | null
  created_at: string
  sources: RagQualitySource[]
  chunks: string[]
  answer_message_id?: string | null
  groundedness_score?: number | null
  groundedness_flag: boolean
  retrieval_quality?: string | null
}

export interface RagQualitySummary {
  retrieval_count: number
  chunk_count: number
  source_count: number
  top_score?: number | null
  groundedness_score?: number | null
  groundedness_flag: boolean
  zero_source: boolean
}

export interface RagQualityFeedbackItem {
  feedback_id: string
  feedback_created_at: string
  feedback_comment?: string | null
  rating: -1 | 1
  message_id?: string | null
  resolved_message_id?: string | null
  thread_id: string
  thread_title: string
  client_user_id?: string | null
  client_email: string
  question: string
  question_message_id?: string | null
  answer: string
  answer_created_at?: string | null
  retrieval_logs: RagQualityRetrievalLog[]
  summary: RagQualitySummary
}

export interface RagQualityThumbsDownResponse {
  items: RagQualityFeedbackItem[]
}

export async function getRagEvalCases(token: string): Promise<RagEvalCase[]> {
  const response = await fetch('/api/admin/rag-evals/cases', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch eval cases failed: ${response.status}`)
  return response.json()
}

async function parseApiError(response: Response, fallback: string): Promise<Error> {
  try {
    const data = await response.json()
    if (typeof data.detail === 'string') return new Error(data.detail)
    if (Array.isArray(data.detail) && data.detail.length > 0) {
      const first = data.detail[0]
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined
      const message = first.msg || fallback
      return new Error(field ? `${field}: ${message}` : message)
    }
  } catch {
    // fall through to fallback
  }
  return new Error(fallback)
}

export async function createRagEvalCase(payload: RagEvalCaseCreate, token: string): Promise<RagEvalCase> {
  const response = await fetch('/api/admin/rag-evals/cases', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw await parseApiError(response, `Create eval case failed: ${response.status}`)
  return response.json()
}

export async function updateRagEvalCase(caseId: string, payload: RagEvalCaseUpdate, token: string): Promise<RagEvalCase> {
  const response = await fetch(`/api/admin/rag-evals/cases/${caseId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw await parseApiError(response, `Update eval case failed: ${response.status}`)
  return response.json()
}

export async function getRagEvalRuns(token: string): Promise<RagEvalRunSummary[]> {
  const response = await fetch('/api/admin/rag-evals/runs', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch eval runs failed: ${response.status}`)
  return response.json()
}

export async function getRagEvalRun(runId: string, token: string): Promise<RagEvalRunDetail> {
  const response = await fetch(`/api/admin/rag-evals/runs/${runId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch eval run failed: ${response.status}`)
  return response.json()
}

export async function getRagQualityThumbsDown(
  token: string,
  params: { limit?: number } = {},
): Promise<RagQualityThumbsDownResponse> {
  const search = new URLSearchParams({ limit: String(params.limit || 50) })
  const response = await fetch(`/api/admin/rag-quality/thumbs-down?${search.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch RAG quality feedback failed: ${response.status}`)
  return response.json()
}

export async function runRagEval(
  payload: { retrieval_mode?: 'vector' | 'fts' | 'hybrid' },
  token: string,
): Promise<RagEvalRunDetail> {
  const response = await fetch('/api/admin/rag-evals/runs', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Run eval failed: ${response.status}`)
  return response.json()
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


// --- Owner Admin Approval API ---

export type OwnerAdminStatus = 'pending' | 'approved' | 'suspended' | 'all'

export interface OwnerTenantSummary {
  id?: string
  name?: string
  slug?: string
  status?: string
}

export interface OwnerAdminProfile {
  id: string
  email: string
  role: string
  status: 'pending' | 'approved' | 'suspended' | string
  tenant_id: string
  created_at: string
  tenant?: OwnerTenantSummary
}

export interface OwnerAdminsResponse {
  admins: OwnerAdminProfile[]
  page: number
  limit: number
  total: number
}

const ownerHeaders = (ownerKey: string) => ({
  'Content-Type': 'application/json',
  'X-Owner-Key': ownerKey,
})

async function parseOwnerError(response: Response, fallback: string): Promise<Error> {
  try {
    const data = await response.json()
    return new Error(data.detail || fallback)
  } catch {
    return new Error(fallback)
  }
}

export async function getOwnerAdmins(
  ownerKey: string,
  params: { status?: OwnerAdminStatus; page?: number; limit?: number } = {},
): Promise<OwnerAdminsResponse> {
  const search = new URLSearchParams({
    status: params.status || 'pending',
    page: String(params.page || 1),
    limit: String(params.limit || 50),
  })
  const response = await fetch(`/api/owner/admins?${search.toString()}`, {
    headers: ownerHeaders(ownerKey),
  })
  if (!response.ok) throw await parseOwnerError(response, `Fetch owner admins failed: ${response.status}`)
  return response.json()
}

export async function approveOwnerAdmin(
  ownerKey: string,
  userId: string,
): Promise<{ status: string; admin: OwnerAdminProfile }> {
  const response = await fetch(`/api/owner/admins/${encodeURIComponent(userId)}/approve`, {
    method: 'POST',
    headers: ownerHeaders(ownerKey),
  })
  if (!response.ok) throw await parseOwnerError(response, `Approve owner admin failed: ${response.status}`)
  return response.json()
}

export async function rejectOwnerAdmin(
  ownerKey: string,
  userId: string,
): Promise<{ status: string; admin: OwnerAdminProfile }> {
  const response = await fetch(`/api/owner/admins/${encodeURIComponent(userId)}/reject`, {
    method: 'POST',
    headers: ownerHeaders(ownerKey),
  })
  if (!response.ok) throw await parseOwnerError(response, `Reject owner admin failed: ${response.status}`)
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


// --- Message Feedback ---

export async function submitFeedback(
  threadId: string,
  messageId: string,
  rating: 1 | -1,
  token: string,
  comment?: string,
): Promise<void> {
  const response = await fetch('/api/chat/feedback', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ thread_id: threadId, message_id: messageId, rating, comment }),
  })
  if (!response.ok) throw new Error(`Submit feedback failed: ${response.status}`)
}

export async function submitWidgetFeedback(
  threadId: string,
  messageId: string,
  rating: 1 | -1,
  token: string,
  comment?: string,
): Promise<void> {
  const response = await fetch('/api/widget/feedback', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ thread_id: threadId, message_id: messageId, rating, comment }),
  })
  if (!response.ok) throw new Error(`Submit widget feedback failed: ${response.status}`)
}

export async function getThreadFeedback(
  threadId: string,
  token: string,
): Promise<Record<string, 1 | -1>> {
  const response = await fetch(`/api/chat/threads/${threadId}/feedback`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Fetch feedback failed: ${response.status}`)
  const data = await response.json()
  const map: Record<string, 1 | -1> = {}
  for (const f of data.feedback || []) {
    map[f.message_id] = f.rating
  }
  return map
}
