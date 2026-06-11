/**
 * localStorage persistence for upload sessions and polling state.
 *
 * Survives page refreshes so chunked uploads can resume and
 * document-status polling can restart after navigation.
 */

const STORAGE_VERSION = 1
const KEY_PREFIX = 'rag_upload_state'

interface PersistedSession {
  sessionId: string
  filename: string
  totalSize: number
  totalChunks: number
  uploadedChunks: number
  useOcr: boolean
  pdfParserMode: string
  startedAt: number
}

interface PersistedPollingDoc {
  documentId: string
  filename: string
  addedAt: number
}

interface PersistedUploadState {
  version: 1
  sessions: PersistedSession[]
  pollingDocumentIds: PersistedPollingDoc[]
}

function storageKey(userId: string): string {
  return `${KEY_PREFIX}_${userId}`
}

export function loadState(userId: string): PersistedUploadState | null {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed.version !== STORAGE_VERSION) return null
    return parsed as PersistedUploadState
  } catch {
    return null
  }
}

export function saveState(userId: string, state: PersistedUploadState): void {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(state))
  } catch {
    // localStorage full or blocked — non-fatal
  }
}

function ensureState(userId: string): PersistedUploadState {
  return loadState(userId) ?? { version: 1, sessions: [], pollingDocumentIds: [] }
}

// --- Session helpers ---

export function addSession(userId: string, session: PersistedSession): void {
  const state = ensureState(userId)
  // Remove any existing entry with the same sessionId
  state.sessions = state.sessions.filter((s) => s.sessionId !== session.sessionId)
  state.sessions.push(session)
  saveState(userId, state)
}

export function updateSessionProgress(userId: string, sessionId: string, uploadedChunks: number): void {
  const state = ensureState(userId)
  const session = state.sessions.find((s) => s.sessionId === sessionId)
  if (session) {
    session.uploadedChunks = uploadedChunks
    saveState(userId, state)
  }
}

export function removeSession(userId: string, sessionId: string): void {
  const state = ensureState(userId)
  state.sessions = state.sessions.filter((s) => s.sessionId !== sessionId)
  saveState(userId, state)
}

export function getSessions(userId: string): PersistedSession[] {
  return ensureState(userId).sessions
}

// --- Polling document helpers ---

export function addPollingDocument(userId: string, doc: PersistedPollingDoc): void {
  const state = ensureState(userId)
  state.pollingDocumentIds = state.pollingDocumentIds.filter((d) => d.documentId !== doc.documentId)
  state.pollingDocumentIds.push(doc)
  saveState(userId, state)
}

export function removePollingDocument(userId: string, documentId: string): void {
  const state = ensureState(userId)
  state.pollingDocumentIds = state.pollingDocumentIds.filter((d) => d.documentId !== documentId)
  saveState(userId, state)
}

export function getPollingDocuments(userId: string): PersistedPollingDoc[] {
  return ensureState(userId).pollingDocumentIds
}

// --- Cleanup ---

export function clearAll(userId: string): void {
  try {
    localStorage.removeItem(storageKey(userId))
  } catch {
    // non-fatal
  }
}

export type { PersistedSession, PersistedPollingDoc, PersistedUploadState }
