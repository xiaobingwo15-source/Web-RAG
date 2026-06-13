import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useDocuments } from '@/hooks/useDocuments'
import { useChunkedUpload } from '@/hooks/useChunkedUpload'
import { useFlaggedNotifications } from '@/hooks/useFlaggedNotifications'
import { DocumentUpload } from '@/components/DocumentUpload'
import {
  getAdminConversations,
  getAdminThreadMessages,
  getFlaggedMessages,
  getAdminSettings,
  submitAdminResponse,
  saveAdminSettings,
  getAdminUsers,
  updateUserStatus,
  getRagEvalCases,
  createRagEvalCase,
  getRagEvalRuns,
  getRagEvalRun,
  runRagEval,
  updateRagEvalCase,
  getRagQualityThumbsDown,
  getRagQualitySignals,
  type AdminClient,
  type AdminMessage,
  type FlaggedMessage,
  type AdminUser,
  type SystemSettings,
  type RagEvalCase,
  type RagEvalRunSummary,
  type RagEvalRunDetail,
  type RagQualityFeedbackItem,
  type RagQualitySignal,
  type RagQualitySignalsResponse,
  type RagQualitySource,
} from '@/lib/api'
import { markInteraction, markRouteReady } from '@/lib/performance'
import {
  Shield,
  LogOut,
  Users,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Search,
  User,
  Bot,
  Database,
  Mail,
  Hash,
  Clock,
  AlertTriangle,
  Settings,
  ClipboardCheck,
  Plus,
  CheckCircle,
  XCircle,
} from 'lucide-react'

export function AdminPage() {
  const { user, session, signOut } = useAuth()
  const navigate = useNavigate()
  const {
    documents,
    uploadDocument,
    deleteDocument,
    addDocumentForPolling,
    isUploading,
    loadError,
    duplicateWarning,
    clearDuplicateWarning,
    uploadFailure,
    clearUploadFailure
  } = useDocuments()

  const {
    upload: chunkedUpload,
    activeUploads,
    pendingResumes,
    resumeUpload,
    cancelUpload,
    dismissResume,
  } = useChunkedUpload()

  const [activeTab, setActiveTab] = useState<'conversations' | 'users' | 'evals' | 'settings'>('conversations')
  const [clients, setClients] = useState<AdminClient[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedClient, setExpandedClient] = useState<string | null>(null)
  const [selectedThread, setSelectedThread] = useState<{ threadId: string; title: string } | null>(null)
  const [threadMessages, setThreadMessages] = useState<AdminMessage[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // Admin Manual Answer state
  const [flaggedFilter, setFlaggedFilter] = useState(false)
  const [flaggedMessages, setFlaggedMessages] = useState<FlaggedMessage[]>([])
  const [responseText, setResponseText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const { flaggedCount, dismissFlag, refreshCount } = useFlaggedNotifications()

  // User Management State
  const [tenantUsers, setTenantUsers] = useState<AdminUser[]>([])
  const [usersLoading, setUsersLoading] = useState(false)
  const [settings, setSettings] = useState<SystemSettings>({})
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null)
  const [evalCases, setEvalCases] = useState<RagEvalCase[]>([])
  const [evalRuns, setEvalRuns] = useState<RagEvalRunSummary[]>([])
  const [selectedEvalRun, setSelectedEvalRun] = useState<RagEvalRunDetail | null>(null)
  const [evalWorkspaceView, setEvalWorkspaceView] = useState<'runs' | 'signals' | 'feedback'>('runs')
  const [qualityFeedback, setQualityFeedback] = useState<RagQualityFeedbackItem[]>([])
  const [ragSignals, setRagSignals] = useState<RagQualitySignalsResponse | null>(null)
  const [selectedQualityFeedbackId, setSelectedQualityFeedbackId] = useState<string | null>(null)
  const [qualityLoading, setQualityLoading] = useState(false)
  const [signalsLoading, setSignalsLoading] = useState(false)
  const [expandedQualityChunks, setExpandedQualityChunks] = useState<Record<string, boolean>>({})
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalRunning, setEvalRunning] = useState(false)
  const [evalMessage, setEvalMessage] = useState<string | null>(null)
  const [editingEvalCaseId, setEditingEvalCaseId] = useState<string | null>(null)
  const [evalForm, setEvalForm] = useState({
    question: '',
    expectedFacts: '',
    expectedAnswer: '',
    expectedDocumentId: '',
    tags: '',
    enabled: true,
    status: 'active' as RagEvalCase['status'],
  })

  useEffect(() => {
    markRouteReady('/admin')
  }, [])

  const switchTab = (tab: 'conversations' | 'users' | 'evals' | 'settings') => {
    markInteraction('admin.tab.switch', { tab })
    setActiveTab(tab)
  }

  const fetchConversations = useCallback(async () => {
    if (!session?.access_token) return
    markInteraction('admin.conversations.refresh')
    setLoading(true)
    try {
      const data = await getAdminConversations(session.access_token)
      setClients(data.clients)
    } catch (err) {
      console.error('Failed to fetch conversations:', err)
    } finally {
      setLoading(false)
    }
  }, [session?.access_token])

  useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  const fetchFlagged = useCallback(async () => {
    if (!session?.access_token) return
    try {
      const data = await getFlaggedMessages(session.access_token)
      setFlaggedMessages(data.flagged)
    } catch (err) {
      console.error('Failed to fetch flagged messages:', err)
    }
  }, [session?.access_token])

  useEffect(() => {
    fetchFlagged()
  }, [fetchFlagged])

  const fetchUsers = useCallback(async () => {
    if (!session?.access_token) return
    markInteraction('admin.users.refresh')
    setUsersLoading(true)
    try {
      const data = await getAdminUsers(session.access_token)
      setTenantUsers(data.users)
    } catch (err) {
      console.error('Failed to fetch users:', err)
    } finally {
      setUsersLoading(false)
    }
  }, [session?.access_token])

  useEffect(() => {
    if (activeTab === 'users') {
      fetchUsers()
    }
  }, [activeTab, fetchUsers])

  const fetchSettings = useCallback(async () => {
    if (!session?.access_token) return
    markInteraction('admin.settings.load')
    setSettingsLoading(true)
    setSettingsMessage(null)
    try {
      const data = await getAdminSettings(session.access_token)
      setSettings(data)
    } catch (err) {
      console.error('Failed to fetch settings:', err)
      setSettingsMessage('Failed to load settings')
    } finally {
      setSettingsLoading(false)
    }
  }, [session?.access_token])

  useEffect(() => {
    if (activeTab === 'settings') {
      fetchSettings()
    }
  }, [activeTab, fetchSettings])

  const fetchEvals = useCallback(async (preferredRunId?: string) => {
    if (!session?.access_token) return
    setEvalLoading(true)
    setEvalMessage(null)
    try {
      const [cases, runs] = await Promise.all([
        getRagEvalCases(session.access_token),
        getRagEvalRuns(session.access_token),
      ])
      setEvalCases(cases)
      setEvalRuns(runs)
      const runId = preferredRunId && runs.some((run) => run.id === preferredRunId)
        ? preferredRunId
        : runs[0]?.id
      if (runId) {
        const detail = await getRagEvalRun(runId, session.access_token)
        setSelectedEvalRun(detail)
      } else {
        setSelectedEvalRun(null)
      }
    } catch (err) {
      console.error('Failed to fetch evals:', err)
      setEvalMessage('Failed to load evals')
    } finally {
      setEvalLoading(false)
    }
  }, [session?.access_token])

  const fetchQualityFeedback = useCallback(async () => {
    if (!session?.access_token) return
    setQualityLoading(true)
    try {
      const data = await getRagQualityThumbsDown(session.access_token, { limit: 50 })
      setQualityFeedback(data.items)
      setSelectedQualityFeedbackId((current) => (
        current && data.items.some((item) => item.feedback_id === current)
          ? current
          : data.items[0]?.feedback_id ?? null
      ))
    } catch (err) {
      console.error('Failed to fetch RAG quality feedback:', err)
      setEvalMessage('Failed to load feedback review')
    } finally {
      setQualityLoading(false)
    }
  }, [session?.access_token])

  const fetchRagSignals = useCallback(async () => {
    if (!session?.access_token) return
    setSignalsLoading(true)
    try {
      const data = await getRagQualitySignals(session.access_token, { window_hours: 168, limit: 50 })
      setRagSignals(data)
    } catch (err) {
      console.error('Failed to fetch RAG quality signals:', err)
      setEvalMessage('Failed to load RAG signals')
    } finally {
      setSignalsLoading(false)
    }
  }, [session?.access_token])

  useEffect(() => {
    if (activeTab === 'evals') {
      fetchEvals()
      fetchRagSignals()
      fetchQualityFeedback()
    }
  }, [activeTab, fetchEvals, fetchQualityFeedback, fetchRagSignals])

  const handleSettingChange = (key: keyof SystemSettings, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const handleSaveSettings = async () => {
    if (!session?.access_token) return
    markInteraction('admin.settings.save')
    setSettingsSaving(true)
    setSettingsMessage(null)
    try {
      await saveAdminSettings(settings, session.access_token)
      setSettingsMessage('Settings saved')
      await fetchSettings()
    } catch (err) {
      console.error('Failed to save settings:', err)
      setSettingsMessage('Failed to save settings')
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleSaveEvalCase = async () => {
    if (!session?.access_token || !evalForm.question.trim()) return
    markInteraction('admin.evals.save_case', { editing: Boolean(editingEvalCaseId) })
    const expectedFacts = splitFactsInput(evalForm.expectedFacts)
    const isDraft = evalForm.status === 'draft'
    if (!isDraft && expectedFacts.length === 0) {
      setEvalMessage('Add at least one expected fact')
      return
    }
    const expectedDocumentId = evalForm.expectedDocumentId.trim()
    if (expectedDocumentId && !isUuid(expectedDocumentId)) {
      setEvalMessage('Expected document ID must be a valid UUID or empty')
      return
    }
    setEvalLoading(true)
    setEvalMessage(null)
    try {
      const payload = {
        question: evalForm.question.trim(),
        expected_facts: expectedFacts,
        expected_answer: evalForm.expectedAnswer.trim() || null,
        expected_document_id: expectedDocumentId || null,
        tags: splitListInput(evalForm.tags),
        enabled: isDraft ? false : evalForm.enabled,
        status: evalForm.status,
      }
      if (editingEvalCaseId) {
        await updateRagEvalCase(editingEvalCaseId, payload, session.access_token)
        setEvalMessage(isDraft ? 'Draft eval case updated' : 'Eval case updated')
      } else {
        await createRagEvalCase(payload, session.access_token)
        setEvalMessage(isDraft ? 'Draft eval case added' : 'Eval case added')
      }
      resetEvalForm()
      await fetchEvals(selectedEvalRun?.run.id)
    } catch (err) {
      console.error('Failed to save eval case:', err)
      setEvalMessage(err instanceof Error ? err.message : 'Failed to save eval case')
    } finally {
      setEvalLoading(false)
    }
  }

  const handleEditEvalCase = (item: RagEvalCase) => {
    setEditingEvalCaseId(item.id)
    setEvalForm({
      question: item.question,
      expectedFacts: item.expected_facts.join('\n'),
      expectedAnswer: item.expected_answer || '',
      expectedDocumentId: item.expected_document_id || '',
      tags: item.tags.join('\n'),
      enabled: item.status === 'draft' ? false : item.enabled,
      status: item.status || 'active',
    })
    setEvalMessage(null)
  }

  const handleToggleEvalCase = async (item: RagEvalCase) => {
    if (!session?.access_token) return
    if (item.status === 'draft') {
      handleEditEvalCase(item)
      setEvalMessage('Review the draft and add expected facts before activating it.')
      return
    }
    if (!item.enabled && item.expected_facts.length === 0) {
      handleEditEvalCase(item)
      setEvalMessage('Add expected facts before enabling this eval case.')
      return
    }
    setEvalLoading(true)
    setEvalMessage(null)
    try {
      await updateRagEvalCase(item.id, { enabled: !item.enabled }, session.access_token)
      if (editingEvalCaseId === item.id) {
        setEvalForm((prev) => ({ ...prev, enabled: !item.enabled }))
      }
      setEvalMessage(!item.enabled ? 'Eval case enabled' : 'Eval case disabled')
      await fetchEvals(selectedEvalRun?.run.id)
    } catch (err) {
      console.error('Failed to update eval case status:', err)
      setEvalMessage(err instanceof Error ? err.message : 'Failed to update eval case status')
    } finally {
      setEvalLoading(false)
    }
  }

  const resetEvalForm = () => {
    setEditingEvalCaseId(null)
    setEvalForm({
      question: '',
      expectedFacts: '',
      expectedAnswer: '',
      expectedDocumentId: '',
      tags: '',
      enabled: true,
      status: 'active',
    })
  }

  const handleRunEval = async () => {
    if (!session?.access_token || evalRunning) return
    markInteraction('admin.evals.run')
    setEvalRunning(true)
    setEvalMessage(null)
    try {
      const detail = await runRagEval({ retrieval_mode: 'hybrid' }, session.access_token)
      setSelectedEvalRun(detail)
      await fetchEvals()
      setEvalMessage('Eval run completed')
    } catch (err) {
      console.error('Failed to run eval:', err)
      setEvalMessage('Eval run failed')
    } finally {
      setEvalRunning(false)
    }
  }

  const handleSelectEvalRun = async (runId: string) => {
    if (!session?.access_token) return
    markInteraction('admin.evals.select_run')
    setEvalLoading(true)
    try {
      const detail = await getRagEvalRun(runId, session.access_token)
      setSelectedEvalRun(detail)
    } catch (err) {
      console.error('Failed to load eval run:', err)
      setEvalMessage('Failed to load eval run')
    } finally {
      setEvalLoading(false)
    }
  }

  const selectedQualityFeedback = useMemo(
    () => qualityFeedback.find((item) => item.feedback_id === selectedQualityFeedbackId) ?? qualityFeedback[0] ?? null,
    [qualityFeedback, selectedQualityFeedbackId],
  )

  const qualityLoopDrafts = useMemo(
    () => evalCases.filter((item) => item.status === 'draft' && item.source_type),
    [evalCases],
  )

  const runnableEvalCases = useMemo(
    () => evalCases.filter((item) => item.enabled && item.status !== 'draft'),
    [evalCases],
  )

  const qualityDraftBySource = useMemo(() => {
    const drafts = new Map<string, RagEvalCase>()
    for (const item of evalCases) {
      if (item.source_type && item.source_ref_id) {
        drafts.set(`${item.source_type}:${item.source_ref_id}`, item)
      }
    }
    return drafts
  }, [evalCases])

  const editingEvalCase = useMemo(
    () => evalCases.find((item) => item.id === editingEvalCaseId) ?? null,
    [evalCases, editingEvalCaseId],
  )

  const selectedFeedbackDraft = useMemo(() => {
    if (!selectedQualityFeedback) return null
    return qualityDraftBySource.get(`thumbs_down_feedback:${selectedQualityFeedback.feedback_id}`) ?? null
  }, [qualityDraftBySource, selectedQualityFeedback])

  const handleSeedEvalCase = (item: RagQualityFeedbackItem) => {
    setEditingEvalCaseId(null)
    setEvalWorkspaceView('runs')
    setEvalForm({
      question: item.question || item.thread_title,
      expectedFacts: '',
      expectedAnswer: '',
      expectedDocumentId: '',
      tags: 'thumbs-down\nquality-loop',
      enabled: false,
      status: 'draft',
    })
    setEvalMessage('Seeded a draft eval case from feedback. Add expected facts before activating.')
  }

  const handleUpdateUserStatus = async (userId: string, action: 'approve' | 'suspend') => {
    if (!session?.access_token) return
    try {
      await updateUserStatus(userId, action, session.access_token)
      await fetchUsers()
    } catch (err) {
      console.error(`Failed to ${action} user:`, err)
    }
  }

  const handleSelectThread = async (threadId: string, title: string) => {
    if (!session?.access_token) return
    markInteraction('admin.thread.select')
    setSelectedThread({ threadId, title })
    setMessagesLoading(true)
    try {
      const data = await getAdminThreadMessages(threadId, session.access_token)
      setThreadMessages(data.messages)
    } catch (err) {
      console.error('Failed to fetch messages:', err)
    } finally {
      setMessagesLoading(false)
    }
  }

  const handleLogout = async () => {
    await signOut()
    navigate('/login')
  }

  const handleSubmitResponse = async () => {
    if (!session?.access_token || !selectedThread || !responseText.trim()) return
    setSubmitting(true)
    try {
      await submitAdminResponse(selectedThread.threadId, responseText, session.access_token)
      setResponseText('')
      // Refresh thread messages to show the admin response
      await handleSelectThread(selectedThread.threadId, selectedThread.title)
      // Refresh flagged data
      dismissFlag()
      await fetchFlagged()
      await refreshCount()
    } catch (err) {
      console.error('Failed to submit admin response:', err)
    } finally {
      setSubmitting(false)
    }
  }

  const toggleClient = (userId: string) => {
    setExpandedClient((prev) => (prev === userId ? null : userId))
  }

  const flaggedThreadIds = useMemo(
    () => new Set(flaggedMessages.map((message) => message.thread_id)),
    [flaggedMessages],
  )

  const filteredClients = useMemo(() => {
    const normalizedQuery = searchQuery.toLowerCase()
    const visibleClients = flaggedFilter
      ? clients
          .filter((client) => client.threads.some((thread) => flaggedThreadIds.has(thread.id)))
          .map((client) => ({
            ...client,
            threads: client.threads.filter((thread) => flaggedThreadIds.has(thread.id)),
          }))
      : clients

    return visibleClients.filter((client) => client.email.toLowerCase().includes(normalizedQuery))
  }, [clients, flaggedFilter, flaggedThreadIds, searchQuery])

  const totalThreads = useMemo(
    () => clients.reduce((sum, client) => sum + client.threads.length, 0),
    [clients],
  )
  const totalMessages = useMemo(
    () => clients.reduce(
      (sum, client) => sum + client.threads.reduce((threadSum, thread) => threadSum + thread.message_count, 0),
      0,
    ),
    [clients],
  )

  return (
    <div className="flex h-screen bg-background">
      {/* ── Left sidebar: WhatsApp-style admin controls ── */}
      <aside className="flex w-80 lg:w-96 flex-col border-r border-border bg-surface shrink-0 overflow-hidden">
        {/* Sidebar header — WhatsApp teal */}
        <div className="flex items-center justify-between px-4 py-3 bg-primary text-primary-foreground">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-white/20 flex items-center justify-center">
              <Shield className="h-5 w-5 text-white" />
            </div>
            <span className="text-sm font-medium">Admin</span>
          </div>
        </div>

        {/* Tab Selector */}
        <div className="flex border-b border-border bg-surface p-1.5 gap-1">
          <button
            onClick={() => switchTab('conversations')}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'conversations'
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            Chats
            {flaggedCount > 0 && (
              <span className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#25D366] text-[9px] font-bold text-white">
                {flaggedCount > 9 ? '9+' : flaggedCount}
              </span>
            )}
          </button>
          <button
            onClick={() => switchTab('users')}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'users'
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            Users
          </button>
          <button
            onClick={() => switchTab('settings')}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'settings'
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Settings className="h-3.5 w-3.5" />
            Settings
          </button>
          <button
            onClick={() => switchTab('evals')}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-all cursor-pointer ${
              activeTab === 'evals'
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <ClipboardCheck className="h-3.5 w-3.5" />
            Evals
          </button>
        </div>

        {/* Collapsible Knowledge Base — open by default, fills space above profile */}
        <div className="border-b border-border flex flex-col flex-1 min-h-0">
          <button
            onClick={() => {
              const el = document.getElementById('kb-section')
              if (el) el.classList.toggle('hidden')
            }}
            className="flex items-center justify-between w-full px-4 py-3 text-sm font-medium text-foreground hover:bg-[#F5F6F6] transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              <span>Knowledge Base</span>
            </div>
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          </button>
          <div id="kb-section" className="flex-1 min-h-0 overflow-hidden">
            <div className="px-4 pb-4 h-full overflow-y-auto">
              <DocumentUpload
                documents={documents}
                isUploading={isUploading}
                onUpload={uploadDocument}
                onDelete={deleteDocument}
                duplicateWarning={duplicateWarning}
                onDismissWarning={clearDuplicateWarning}
                uploadFailure={uploadFailure}
                onDismissFailure={clearUploadFailure}
                loadError={loadError}
                token={session?.access_token}
                chunkedUpload={chunkedUpload}
                activeUploads={activeUploads}
                pendingResumes={pendingResumes}
                onResumeUpload={resumeUpload}
                onCancelUpload={cancelUpload}
                onDismissResume={dismissResume}
                onUploadComplete={addDocumentForPolling}
              />
            </div>
          </div>
        </div>

        {/* User footer */}
        <div className="mt-auto border-t border-border px-4 py-3 bg-surface">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
              <span className="text-sm font-semibold text-primary">
                {user?.email?.[0].toUpperCase() ?? 'A'}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">{user?.email ?? 'Admin'}</p>
              <p className="text-xs text-muted-foreground">Administrator</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Right Panel: Content area ── */}
      {activeTab === 'conversations' ? (
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Top bar — WhatsApp header style */}
          <div className="flex items-center justify-between border-b border-border px-6 py-2.5 bg-surface">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
                <Users className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h1 className="text-sm font-medium text-foreground">Client Conversations</h1>
                <p className="text-xs text-muted-foreground">
                  {clients.length} client{clients.length !== 1 ? 's' : ''} · {totalThreads} thread{totalThreads !== 1 ? 's' : ''} · {totalMessages} message{totalMessages !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setFlaggedFilter((prev) => !prev)
                  if (!flaggedFilter) fetchFlagged()
                }}
                className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors ${
                  flaggedFilter
                    ? 'border-destructive/50 bg-destructive/10 text-destructive'
                    : 'border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                Flagged {flaggedCount > 0 && `(${flaggedCount})`}
              </button>
              <button
                onClick={fetchConversations}
                disabled={loading}
                className="flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          <div className="flex flex-1 overflow-hidden">
            {/* ── Left: Client / Thread List ── */}
            <div className="w-80 flex-shrink-0 border-r border-border bg-card/30 flex flex-col">
              {/* Search */}
              <div className="p-3 border-b border-border">
                <div className="relative">
                  <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search clients..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full rounded-md border border-border bg-input pl-8 pr-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* Client list */}
              <div className="flex-1 overflow-y-auto">
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : filteredClients.length === 0 ? (
                  <div className="py-12 text-center text-xs text-muted-foreground">
                    {searchQuery ? 'No clients match your search' : 'No client conversations yet'}
                  </div>
                ) : (
                  filteredClients.map((client) => (
                    <div key={client.user_id} className="border-b border-border/50">
                      {/* Client header */}
                      <button
                        onClick={() => toggleClient(client.user_id)}
                        className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-muted/50 transition-colors"
                      >
                        {expandedClient === client.user_id ? (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                        )}
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 flex-shrink-0">
                          <Mail className="h-3.5 w-3.5 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="truncate text-xs font-medium text-foreground">
                            {client.email}
                          </p>
                          <p className="text-[10px] text-muted-foreground">
                            {client.threads.length} conversation{client.threads.length !== 1 ? 's' : ''}
                          </p>
                        </div>
                      </button>

                      {/* Thread list (expanded) */}
                      {expandedClient === client.user_id && (
                        <div className="bg-muted/20 pb-1">
                          {client.threads.map((thread) => (
                            <button
                              key={thread.id}
                              onClick={() => handleSelectThread(thread.id, thread.title)}
                              className={`flex w-full items-center gap-2 px-4 pl-10 py-2 text-left transition-colors ${
                                selectedThread?.threadId === thread.id
                                  ? 'bg-primary/10 text-primary'
                                  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                              }`}
                            >
                              <MessageSquare className="h-3.5 w-3.5 flex-shrink-0" />
                              <div className="flex-1 min-w-0">
                                <p className="truncate text-xs">{thread.title}</p>
                                <div className="flex items-center gap-2 mt-0.5">
                                  <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                                    <Hash className="h-2.5 w-2.5" />
                                    {thread.message_count} msgs
                                  </span>
                                  <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                                    <Clock className="h-2.5 w-2.5" />
                                    {new Date(thread.created_at).toLocaleDateString(undefined, {
                                      month: 'short',
                                      day: 'numeric',
                                    })}
                                  </span>
                                </div>
                              </div>
                              {flaggedMessages.some((f) => f.thread_id === thread.id) && (
                                <div className="h-2 w-2 rounded-full bg-destructive animate-pulse flex-shrink-0" />
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* ── Right: Message Viewer ── */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {selectedThread ? (
                <>
                  {/* Thread header */}
                  <div className="flex items-center gap-2 border-b border-border px-5 py-3 bg-card/30">
                    <MessageSquare className="h-4 w-4 text-primary" />
                    <div>
                      <p className="text-sm font-medium text-foreground">{selectedThread.title}</p>
                      <p className="text-[10px] text-muted-foreground">
                        Thread ID: {selectedThread.threadId.slice(0, 8)}...
                      </p>
                    </div>
                  </div>

                  {/* Messages */}
                  <div className="flex-1 overflow-y-auto p-5">
                    {messagesLoading ? (
                      <div className="flex items-center justify-center py-12">
                        <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    ) : threadMessages.length === 0 ? (
                      <div className="py-12 text-center text-xs text-muted-foreground">
                        No messages in this thread
                      </div>
                    ) : (
                      <div className="mx-auto max-w-3xl space-y-3">
                        {threadMessages.map((msg) => {
                          const isAdmin = msg.role === 'admin'
                          const isUser = msg.role === 'user'
                          const isFlagged = flaggedMessages.some((f) => f.message_id === msg.id)

                          return (
                            <div
                              key={msg.id}
                              className={`flex gap-3 rounded-xl p-4 ${
                                isAdmin
                                  ? 'bg-amber-500/5 border border-amber-500/20'
                                  : isUser
                                    ? 'bg-primary/5 border border-primary/10'
                                    : 'bg-muted/30 border border-border/50'
                              }`}
                            >
                              <div
                                className={`flex h-7 w-7 items-center justify-center rounded-full flex-shrink-0 ${
                                  isAdmin
                                    ? 'bg-amber-500/20 text-amber-500'
                                    : isUser
                                      ? 'bg-primary/20 text-primary'
                                      : 'bg-muted text-muted-foreground'
                                }`}
                              >
                                {isAdmin ? (
                                  <Shield className="h-3.5 w-3.5" />
                                ) : isUser ? (
                                  <User className="h-3.5 w-3.5" />
                                ) : (
                                  <Bot className="h-3.5 w-3.5" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1.5">
                                  <span
                                    className={`text-xs font-semibold ${
                                      isAdmin
                                        ? 'text-amber-500'
                                        : isUser
                                          ? 'text-primary'
                                          : 'text-muted-foreground'
                                    }`}
                                  >
                                    {isAdmin ? 'Admin' : isUser ? 'Client' : 'Assistant'}
                                  </span>
                                  <span className="text-[10px] text-muted-foreground/60">
                                    {new Date(msg.created_at).toLocaleString(undefined, {
                                      month: 'short',
                                      day: 'numeric',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    })}
                                  </span>
                                </div>
                                <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                                  {msg.content}
                                </p>
                                {isFlagged && (
                                  <div className="flex items-center gap-1 text-[10px] text-destructive mt-2">
                                    <AlertTriangle className="h-3 w-3" />
                                    Flagged for review
                                  </div>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* Admin response input */}
                  {selectedThread &&
                    flaggedMessages.some(
                      (f) => f.thread_id === selectedThread.threadId && !f.has_admin_response,
                    ) && (
                      <div className="border-t border-border p-4 bg-card/50">
                        <div className="mx-auto max-w-3xl">
                          <p className="text-xs text-muted-foreground mb-2">
                            <Shield className="inline h-3 w-3 mr-1" />
                            Respond as admin to this flagged conversation
                          </p>
                          <div className="flex gap-2">
                            <textarea
                              value={responseText}
                              onChange={(e) => setResponseText(e.target.value)}
                              rows={2}
                              placeholder="Type your manual response..."
                              className="flex-1 resize-none rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                            />
                            <button
                              onClick={handleSubmitResponse}
                              disabled={submitting || !responseText.trim()}
                              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
                            >
                              {submitting ? 'Sending...' : 'Send'}
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                </>
              ) : (
                <div className="flex flex-1 items-center justify-center">
                  <div className="text-center">
                    <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-muted/50 border border-border">
                      <MessageSquare className="h-7 w-7 text-muted-foreground" />
                    </div>
                    <h3 className="text-sm font-medium text-foreground">
                      Select a conversation
                    </h3>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Choose a client and thread from the left panel to view their conversation
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </main>
      ) : activeTab === 'users' ? (
        /* ── User Management ── */
        <main className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-card/50">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Users className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground">User Management</h1>
                <p className="text-[10px] text-muted-foreground">
                  {tenantUsers.length} user{tenantUsers.length !== 1 ? 's' : ''} in your organization
                </p>
              </div>
            </div>
            <button
              onClick={fetchUsers}
              disabled={usersLoading}
              className="flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${usersLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-6 bg-card/10">
            <div className="mx-auto max-w-4xl">
              {usersLoading ? (
                <div className="flex h-64 items-center justify-center">
                  <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : tenantUsers.length === 0 ? (
                <div className="flex h-64 items-center justify-center">
                  <p className="text-xs text-muted-foreground">No users found</p>
                </div>
              ) : (
                <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
                  {/* Table header */}
                  <div className="grid grid-cols-[1fr_80px_100px_120px_120px] gap-4 px-5 py-2.5 border-b border-border bg-muted/30 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                    <span>Email</span>
                    <span>Role</span>
                    <span>Status</span>
                    <span>Joined</span>
                    <span>Actions</span>
                  </div>
                  {/* Table rows */}
                  {tenantUsers.map((u) => (
                    <div
                      key={u.id}
                      className="grid grid-cols-[1fr_80px_100px_120px_120px] gap-4 items-center px-5 py-3 border-b border-border/50 hover:bg-muted/20 transition-colors"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 flex-shrink-0">
                          <User className="h-3.5 w-3.5 text-primary" />
                        </div>
                        <span className="truncate text-xs text-foreground">{u.email}</span>
                      </div>
                      <span className={`text-xs font-medium ${u.role === 'admin' ? 'text-amber-500' : 'text-muted-foreground'}`}>
                        {u.role}
                      </span>
                      <span>
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                          u.status === 'approved'
                            ? 'bg-green-500/10 text-green-500'
                            : u.status === 'pending'
                              ? 'bg-amber-500/10 text-amber-500'
                              : 'bg-destructive/10 text-destructive'
                        }`}>
                          {u.status}
                        </span>
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(u.created_at).toLocaleDateString(undefined, {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {u.id === user?.id ? (
                          <span className="text-[10px] text-muted-foreground italic">You</span>
                        ) : u.status === 'pending' || u.status === 'suspended' ? (
                          <button
                            onClick={() => handleUpdateUserStatus(u.id, 'approve')}
                            className="rounded-md bg-green-500/10 px-2.5 py-1 text-[10px] font-semibold text-green-500 hover:bg-green-500/20 transition-colors cursor-pointer"
                          >
                            Approve
                          </button>
                        ) : (
                          <button
                            onClick={() => handleUpdateUserStatus(u.id, 'suspend')}
                            className="rounded-md bg-destructive/10 px-2.5 py-1 text-[10px] font-semibold text-destructive hover:bg-destructive/20 transition-colors cursor-pointer"
                          >
                            Suspend
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </main>
      ) : activeTab === 'evals' ? (
        <main className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-card/50">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <ClipboardCheck className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground">RAG Evaluation</h1>
                <p className="text-[10px] text-muted-foreground">
                  {runnableEvalCases.length} runnable · {qualityLoopDrafts.length} draft{qualityLoopDrafts.length !== 1 ? 's' : ''} · {evalRuns.length} run{evalRuns.length !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  fetchEvals()
                  fetchRagSignals()
                  fetchQualityFeedback()
                }}
                disabled={evalLoading || evalRunning || qualityLoading || signalsLoading}
                className="flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${evalLoading || qualityLoading || signalsLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <button
                onClick={handleRunEval}
                disabled={evalRunning || runnableEvalCases.length === 0}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                <ClipboardCheck className="h-3.5 w-3.5" />
                {evalRunning ? 'Running...' : 'Run RAG Eval'}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 bg-card/10">
            <div className="mx-auto max-w-6xl space-y-5">
              {evalMessage && (
                <div className="rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">{evalMessage}</div>
              )}

              <div className="inline-flex rounded-lg border border-border bg-card p-1">
                <button
                  onClick={() => setEvalWorkspaceView('runs')}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    evalWorkspaceView === 'runs'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  Eval Runs
                </button>
                <button
                  onClick={() => setEvalWorkspaceView('signals')}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    evalWorkspaceView === 'signals'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  RAG Signals
                  {ragSignals && (
                    <span className="ml-1 text-[10px] opacity-80">
                      ({ragSignals.signals.filter((signal) => signal.status !== 'ok').length})
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setEvalWorkspaceView('feedback')}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    evalWorkspaceView === 'feedback'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  Feedback Review
                  {qualityFeedback.length > 0 && (
                    <span className="ml-1 text-[10px] opacity-80">({qualityFeedback.length})</span>
                  )}
                </button>
              </div>

              {evalWorkspaceView === 'runs' ? (
                <>
              <section className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-foreground">
                    {editingEvalCaseId ? 'Edit Eval Case' : 'Eval Cases'}
                  </h2>
                  <span className="text-[10px] text-muted-foreground">{runnableEvalCases.length} runnable</span>
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <label className="text-xs text-muted-foreground md:col-span-2">
                    Question
                    <textarea
                      rows={2}
                      value={evalForm.question}
                      onChange={(e) => setEvalForm((prev) => ({ ...prev, question: e.target.value }))}
                      className="mt-1 w-full resize-none rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground"
                      placeholder="What fact should the assistant answer from the knowledge base?"
                    />
                  </label>
                  <label className="text-xs text-muted-foreground md:col-span-2">
                    Expected facts
                    <textarea
                      rows={2}
                      value={evalForm.expectedFacts}
                      onChange={(e) => setEvalForm((prev) => ({ ...prev, expectedFacts: e.target.value }))}
                      className="mt-1 w-full resize-none rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground"
                      placeholder="One expected fact per line"
                    />
                  </label>
                  <SettingInput label="Expected answer" value={evalForm.expectedAnswer} onChange={(v) => setEvalForm((prev) => ({ ...prev, expectedAnswer: v }))} />
                  <SettingInput label="Expected document ID" value={evalForm.expectedDocumentId} onChange={(v) => setEvalForm((prev) => ({ ...prev, expectedDocumentId: v }))} />
                  <SettingInput label="Tags" value={evalForm.tags} onChange={(v) => setEvalForm((prev) => ({ ...prev, tags: v }))} placeholder="billing, policy" />
                  <label className="text-xs text-muted-foreground">
                    Status
                    <select
                      value={evalForm.status}
                      onChange={(e) => {
                        const status = e.target.value as RagEvalCase['status']
                        setEvalForm((prev) => ({
                          ...prev,
                          status,
                          enabled: status === 'draft' ? false : prev.enabled,
                        }))
                      }}
                      className="mt-1 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground"
                    >
                      <option value="active">Active</option>
                      <option value="draft">Draft</option>
                    </select>
                  </label>
                  <label className="flex items-center gap-2 pt-6 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={evalForm.enabled}
                      disabled={evalForm.status === 'draft'}
                      onChange={(e) => setEvalForm((prev) => ({ ...prev, enabled: e.target.checked }))}
                    />
                    Enabled
                  </label>
                </div>
                {editingEvalCase?.source_type && editingEvalCase.source_type !== 'manual' && (
                  <EvalCaseSourceReview item={editingEvalCase} />
                )}
                <div className="mt-3 flex justify-end gap-2">
                  {editingEvalCaseId && (
                    <button
                      onClick={resetEvalForm}
                      disabled={evalLoading}
                      className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    onClick={handleSaveEvalCase}
                    disabled={evalLoading || !evalForm.question.trim()}
                    className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    {editingEvalCaseId ? 'Save Changes' : 'Add Case'}
                  </button>
                </div>

                <div className="mt-4 overflow-hidden rounded-lg border border-border">
                  <div className="grid grid-cols-[1fr_220px_120px_90px_150px] gap-3 border-b border-border bg-muted/30 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <span>Question</span>
                    <span>Expected Facts</span>
                    <span>Source</span>
                    <span>Status</span>
                    <span>Actions</span>
                  </div>
                  {evalCases.length === 0 ? (
                    <div className="px-4 py-8 text-center text-xs text-muted-foreground">No eval cases yet</div>
                  ) : (
                    evalCases.map((item) => (
                      <div
                        key={item.id}
                        className={`grid grid-cols-[1fr_220px_120px_90px_150px] items-center gap-3 border-b border-border/50 px-4 py-3 text-xs ${
                          editingEvalCaseId === item.id ? 'bg-primary/5' : ''
                        }`}
                      >
                        <span className="text-foreground">{item.question}</span>
                        <span className="truncate text-muted-foreground">{item.expected_facts.length ? item.expected_facts.join(' · ') : 'Needs expected facts'}</span>
                        <span className="truncate text-muted-foreground">{formatEvalCaseSource(item)}</span>
                        <EvalCaseStatusCell item={item} />
                        <span className="flex items-center gap-1.5">
                          <button
                            onClick={() => handleEditEvalCase(item)}
                            className="rounded-md border border-border bg-background px-2 py-1 text-[10px] font-semibold text-muted-foreground hover:bg-muted hover:text-foreground"
                          >
                            {item.status === 'draft' ? 'Review' : 'Edit'}
                          </button>
                          {item.status !== 'draft' && (
                            <button
                              onClick={() => handleToggleEvalCase(item)}
                              disabled={evalLoading}
                              className={`rounded-md px-2 py-1 text-[10px] font-semibold disabled:opacity-50 ${
                                item.enabled
                                  ? 'bg-muted text-muted-foreground hover:bg-muted/70'
                                  : 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                              }`}
                            >
                              {item.enabled ? 'Disable' : 'Enable'}
                            </button>
                          )}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="grid gap-5 lg:grid-cols-[420px_1fr]">
                <div className="rounded-lg border border-border bg-card p-4">
                  <h2 className="text-sm font-semibold text-foreground">Run History</h2>
                  <div className="mt-3 space-y-2">
                    {evalRuns.length === 0 ? (
                      <div className="py-8 text-center text-xs text-muted-foreground">No eval runs yet</div>
                    ) : (
                      evalRuns.map((run) => {
                        const passRate = run.total_cases ? Math.round((run.passed_cases / run.total_cases) * 100) : 0
                        return (
                          <button
                            key={run.id}
                            onClick={() => handleSelectEvalRun(run.id)}
                            className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                              selectedEvalRun?.run.id === run.id
                                ? 'border-primary bg-primary/5'
                                : 'border-border bg-background hover:bg-muted/40'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="text-xs font-semibold text-foreground">{passRate}% pass</span>
                              <StatusPill status={run.status} />
                            </div>
                            <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
                              <span>{run.passed_cases}/{run.total_cases} cases · {run.retrieval_mode}</span>
                              <span>{new Date(run.created_at).toLocaleString()}</span>
                            </div>
                          </button>
                        )
                      })
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-border bg-card p-4">
                  <h2 className="text-sm font-semibold text-foreground">Run Details</h2>
                  {!selectedEvalRun ? (
                    <div className="py-12 text-center text-xs text-muted-foreground">Select or run an eval to inspect results</div>
                  ) : (
                    <div className="mt-3 space-y-4">
                      <div className="grid gap-2 sm:grid-cols-3">
                        <ScoreTile label="Context" value={selectedEvalRun.run.avg_context_relevance_score} />
                        <ScoreTile label="Groundedness" value={selectedEvalRun.run.avg_groundedness_score} />
                        <ScoreTile label="Answer" value={selectedEvalRun.run.avg_answer_relevance_score} />
                      </div>
                      <div className="space-y-3">
                        {selectedEvalRun.results.map((result) => (
                          <div key={result.id} className="rounded-md border border-border bg-background p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-xs font-semibold text-foreground">{result.question}</p>
                                {result.failure_reason && (
                                  <p className="mt-1 text-[10px] text-destructive">{result.failure_reason}</p>
                                )}
                              </div>
                              {result.passed ? (
                                <CheckCircle className="h-4 w-4 flex-shrink-0 text-green-500" />
                              ) : (
                                <XCircle className="h-4 w-4 flex-shrink-0 text-destructive" />
                              )}
                            </div>
                            <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-xs text-muted-foreground">{result.answer}</p>
                            <div className="mt-3 space-y-2">
                              {result.sources.length === 0 ? (
                                <p className="text-[10px] text-muted-foreground">No sources returned</p>
                              ) : (
                                result.sources.map((source) => (
                                  <div key={`${source.document_id}-${source.chunk_id}`} className="rounded border border-border/70 bg-muted/20 px-2 py-1.5">
                                    <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                                      <span className="truncate">{source.filename || source.document_id}</span>
                                      <span>{source.score.toFixed(3)} · {source.retrieval_mode}</span>
                                    </div>
                                    <p className="mt-1 line-clamp-2 text-[11px] text-foreground">{source.snippet}</p>
                                  </div>
                                ))
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </section>
                </>
              ) : evalWorkspaceView === 'signals' ? (
                <RagSignalsPanel
                  data={ragSignals}
                  loading={signalsLoading}
                  draftCount={qualityLoopDrafts.length}
                  onReviewDrafts={() => setEvalWorkspaceView('runs')}
                />
              ) : (
                <section className="grid gap-5 lg:grid-cols-[380px_1fr]">
                  <div className="rounded-lg border border-border bg-card p-4">
                    <div className="flex items-center justify-between gap-3">
                      <h2 className="text-sm font-semibold text-foreground">Recent Thumbs-Down</h2>
                      <span className="text-[10px] text-muted-foreground">{qualityFeedback.length} item{qualityFeedback.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="mt-3 space-y-2">
                      {qualityLoading ? (
                        <div className="flex justify-center py-10">
                          <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
                        </div>
                      ) : qualityFeedback.length === 0 ? (
                        <div className="py-10 text-center text-xs text-muted-foreground">No thumbs-down feedback yet</div>
                      ) : (
                        qualityFeedback.map((item) => (
                          <button
                            key={item.feedback_id}
                            onClick={() => setSelectedQualityFeedbackId(item.feedback_id)}
                            className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                              selectedQualityFeedback?.feedback_id === item.feedback_id
                                ? 'border-primary bg-primary/5'
                                : 'border-border bg-background hover:bg-muted/40'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <span className="line-clamp-2 text-xs font-semibold text-foreground">
                                {item.question || item.thread_title}
                              </span>
                              {(item.summary.groundedness_flag || item.summary.zero_source) && (
                                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 text-destructive" />
                              )}
                            </div>
                            <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                              <span className="truncate">{item.client_email}</span>
                              <span>{new Date(item.feedback_created_at).toLocaleDateString()}</span>
                            </div>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              <QualityPill active={item.summary.zero_source} label="No sources" />
                              <QualityPill active={item.summary.groundedness_flag} label="Grounding" />
                              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                                {item.summary.source_count} source{item.summary.source_count !== 1 ? 's' : ''}
                              </span>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-card p-4">
                    {!selectedQualityFeedback ? (
                      <div className="py-12 text-center text-xs text-muted-foreground">
                        {qualityLoading ? (
                          <span className="inline-flex items-center gap-2">
                            <RefreshCw className="h-4 w-4 animate-spin" />
                            Loading feedback review...
                          </span>
                        ) : (
                          'Select feedback to inspect retrieval evidence'
                        )}
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <h2 className="text-sm font-semibold text-foreground">{selectedQualityFeedback.thread_title}</h2>
                            <p className="mt-1 text-[10px] text-muted-foreground">
                              {selectedQualityFeedback.client_email} · {new Date(selectedQualityFeedback.feedback_created_at).toLocaleString()}
                            </p>
                          </div>
                          <button
                            onClick={() => {
                              if (selectedFeedbackDraft) {
                                handleEditEvalCase(selectedFeedbackDraft)
                                setEvalWorkspaceView('runs')
                              } else {
                                handleSeedEvalCase(selectedQualityFeedback)
                              }
                            }}
                            className="flex flex-shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90"
                          >
                            <Plus className="h-3.5 w-3.5" />
                            {selectedFeedbackDraft ? 'Review draft' : 'Seed draft'}
                          </button>
                        </div>

                        <div className="grid gap-2 sm:grid-cols-4">
                          <SummaryTile label="Retrievals" value={String(selectedQualityFeedback.summary.retrieval_count)} />
                          <SummaryTile label="Sources" value={String(selectedQualityFeedback.summary.source_count)} />
                          <SummaryTile label="Top Score" value={formatNullableScore(selectedQualityFeedback.summary.top_score)} />
                          <SummaryTile label="Grounded" value={formatPercent(selectedQualityFeedback.summary.groundedness_score)} />
                        </div>

                        <div className="grid gap-3 md:grid-cols-2">
                          <div className="rounded-md border border-border bg-background p-3">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Question</p>
                            <p className="mt-2 whitespace-pre-wrap text-xs text-foreground">{selectedQualityFeedback.question || 'No preceding user question resolved'}</p>
                          </div>
                          <div className="rounded-md border border-border bg-background p-3">
                            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Feedback</p>
                            <p className="mt-2 whitespace-pre-wrap text-xs text-foreground">{selectedQualityFeedback.feedback_comment || 'Thumbs-down without comment'}</p>
                          </div>
                        </div>

                        <div className="rounded-md border border-border bg-background p-3">
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Assistant Answer</p>
                          <p className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-foreground">{selectedQualityFeedback.answer}</p>
                        </div>

                        <div className="space-y-3">
                          <h3 className="text-xs font-semibold text-foreground">Retrieval Logs</h3>
                          {selectedQualityFeedback.retrieval_logs.length === 0 ? (
                            <div className="rounded-md border border-border bg-background p-4 text-center text-xs text-muted-foreground">
                              No retrieval logs resolved for this answer
                            </div>
                          ) : (
                            selectedQualityFeedback.retrieval_logs.map((log) => (
                              <div key={log.id} className="rounded-md border border-border bg-background p-3">
                                <div className="flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
                                  <span className="truncate">{log.query}</span>
                                  <span className="flex-shrink-0">{log.retrieval_mode} · {formatNullableScore(log.top_score)}</span>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  <QualityPill active={log.source_count === 0} label="No sources" />
                                  <QualityPill active={log.groundedness_flag} label="Grounding flag" />
                                  {log.retrieval_quality && (
                                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{log.retrieval_quality}</span>
                                  )}
                                  {log.duration_ms !== null && log.duration_ms !== undefined && (
                                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{log.duration_ms}ms</span>
                                  )}
                                </div>
                              </div>
                            ))
                          )}
                        </div>

                        <div className="space-y-3">
                          <h3 className="text-xs font-semibold text-foreground">Retrieved Documents & Chunks</h3>
                          {groupQualitySources(selectedQualityFeedback).length === 0 ? (
                            <div className="rounded-md border border-border bg-background p-4 text-center text-xs text-muted-foreground">
                              No source chunks were captured
                            </div>
                          ) : (
                            groupQualitySources(selectedQualityFeedback).map((group) => (
                              <div key={group.key} className="rounded-md border border-border bg-background p-3">
                                <div className="flex items-center justify-between gap-3">
                                  <p className="truncate text-xs font-semibold text-foreground">{group.label}</p>
                                  <span className="text-[10px] text-muted-foreground">{group.sources.length} chunk{group.sources.length !== 1 ? 's' : ''}</span>
                                </div>
                                <div className="mt-2 space-y-2">
                                  {group.sources.map((source, index) => (
                                    <QualityChunkPreview
                                      key={`${group.key}-${source.chunk_id || index}`}
                                      source={source}
                                      expanded={Boolean(expandedQualityChunks[`${selectedQualityFeedback.feedback_id}-${group.key}-${source.chunk_id || index}`])}
                                      onToggle={() => {
                                        const key = `${selectedQualityFeedback.feedback_id}-${group.key}-${source.chunk_id || index}`
                                        setExpandedQualityChunks((prev) => ({ ...prev, [key]: !prev[key] }))
                                      }}
                                    />
                                  ))}
                                </div>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              )}
            </div>
          </div>
        </main>
      ) : (
        <main className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-card/50">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Settings className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground">AI & Retrieval Settings</h1>
                <p className="text-[10px] text-muted-foreground">Configure generation, reranking, vector storage, search, and observability.</p>
              </div>
            </div>
            <button
              onClick={handleSaveSettings}
              disabled={settingsSaving || settingsLoading}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {settingsSaving ? 'Saving...' : 'Save'}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-6 bg-card/10">
            <div className="mx-auto max-w-4xl space-y-5">
              {settingsMessage && (
                <div className="rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">{settingsMessage}</div>
              )}
              {settingsLoading ? (
                <div className="flex h-64 items-center justify-center">
                  <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <>
                  <section className="rounded-lg border border-border bg-card p-4">
                    <h2 className="text-sm font-semibold text-foreground">Model Provider</h2>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <label className="text-xs text-muted-foreground">
                        Provider
                        <select
                          value={settings.MODEL_PROVIDER || 'openrouter'}
                          onChange={(e) => handleSettingChange('MODEL_PROVIDER', e.target.value)}
                          className="mt-1 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground"
                        >
                          <option value="openrouter">OpenRouter</option>
                          <option value="mistral">Mistral</option>
                        </select>
                      </label>
                      <SettingInput label="Mistral model" value={settings.MISTRAL_MODEL || ''} onChange={(v) => handleSettingChange('MISTRAL_MODEL', v)} placeholder="mistral-large-latest" />
                      <SettingInput label="Mistral API key" value={settings.MISTRAL_API_KEY || ''} onChange={(v) => handleSettingChange('MISTRAL_API_KEY', v)} placeholder="Paste to replace saved key" />
                      <SettingInput label="OpenRouter API key" value={settings.OPENROUTER_API_KEY || ''} onChange={(v) => handleSettingChange('OPENROUTER_API_KEY', v)} placeholder="Paste to replace saved key" />
                      <SettingInput label="OpenRouter model" value={settings.OPENROUTER_MODEL || ''} onChange={(v) => handleSettingChange('OPENROUTER_MODEL', v)} placeholder="deepseek/deepseek-v4-flash" />
                      <SettingInput label="OpenRouter fallback" value={settings.OPENROUTER_FALLBACK_MODEL || ''} onChange={(v) => handleSettingChange('OPENROUTER_FALLBACK_MODEL', v)} placeholder="deepseek/deepseek-v4-flash:free" />
                      <SettingInput label="OCR model" value={settings.OCR_MODEL || ''} onChange={(v) => handleSettingChange('OCR_MODEL', v)} placeholder="google/gemini-2.5-flash-lite" />
                    </div>
                  </section>

                  <section className="rounded-lg border border-border bg-card p-4">
                    <h2 className="text-sm font-semibold text-foreground">PDF Processing</h2>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <SettingInput label="PDF OCR max pages" value={settings.PDF_OCR_MAX_PAGES || ''} onChange={(v) => handleSettingChange('PDF_OCR_MAX_PAGES', v)} placeholder="20" />
                      <SettingInput label="PDF layout max pages" value={settings.PDF_LAYOUT_MAX_PAGES || ''} onChange={(v) => handleSettingChange('PDF_LAYOUT_MAX_PAGES', v)} placeholder="30" />
                    </div>
                  </section>

                  <section className="rounded-lg border border-border bg-card p-4">
                    <h2 className="text-sm font-semibold text-foreground">Retrieval Stack</h2>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <SettingInput label="Google API key" value={settings.GOOGLE_API_KEY || ''} onChange={(v) => handleSettingChange('GOOGLE_API_KEY', v)} placeholder="Embeddings key" />
                      <SettingInput label="Cohere API key" value={settings.COHERE_API_KEY || ''} onChange={(v) => handleSettingChange('COHERE_API_KEY', v)} placeholder="Reranker key" />
                      <SettingInput label="Qdrant URL" value={settings.QDRANT_URL || ''} onChange={(v) => handleSettingChange('QDRANT_URL', v)} placeholder="https://..." />
                      <SettingInput label="Qdrant API key" value={settings.QDRANT_API_KEY || ''} onChange={(v) => handleSettingChange('QDRANT_API_KEY', v)} placeholder="Paste to replace saved key" />
                    </div>
                  </section>

                  <section className="rounded-lg border border-border bg-card p-4">
                    <h2 className="text-sm font-semibold text-foreground">Search & Observability</h2>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <SettingInput label="Tavily API key" value={settings.TAVLY_API_KEY || ''} onChange={(v) => handleSettingChange('TAVLY_API_KEY', v)} placeholder="Web search key" />
                      <SettingInput label="Langfuse public key" value={settings.LANGFUSE_PUBLIC_KEY || ''} onChange={(v) => handleSettingChange('LANGFUSE_PUBLIC_KEY', v)} />
                      <SettingInput label="Langfuse secret key" value={settings.LANGFUSE_SECRET_KEY || ''} onChange={(v) => handleSettingChange('LANGFUSE_SECRET_KEY', v)} placeholder="Paste to replace saved key" />
                      <SettingInput label="Langfuse URL" value={settings.LANGFUSE_BASE_URL || ''} onChange={(v) => handleSettingChange('LANGFUSE_BASE_URL', v)} placeholder="https://jp.cloud.langfuse.com" />
                    </div>
                  </section>
                </>
              )}
            </div>
          </div>
        </main>
      )}
    </div>
  )
}

function SettingInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  return (
    <label className="text-xs text-muted-foreground">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-md border border-border bg-input px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground"
      />
    </label>
  )
}

function splitListInput(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function splitFactsInput(value: string): string[] {
  return value
    .split(/\n/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}

function EvalCaseSourceReview({ item }: { item: RagEvalCase }) {
  const metadata = asRecord(item.retrieval_metadata)
  const feedback = asRecord(metadata.feedback)
  const fallback = asRecord(metadata.fallback)
  const conversation = asRecord(metadata.conversation)
  const answer = asRecord(metadata.answer)
  const retrieval = asRecord(metadata.retrieval)
  const summary = asRecord(retrieval.summary)
  const logs = asRecordArray(retrieval.logs)

  return (
    <div className="mt-4 rounded-md border border-border bg-background p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold text-foreground">Quality Loop Source</h3>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {sourceTypeLabel(item.source_type)} · {item.source_ref_id || 'no source reference'}
          </p>
        </div>
        <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-500">
          Draft review
        </span>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-4">
        <SummaryTile label="Retrievals" value={displayMetadataValue(summary.retrieval_count ?? fallback.fallback_count)} />
        <SummaryTile label="Sources" value={displayMetadataValue(summary.source_count)} />
        <SummaryTile label="Top Score" value={formatMetadataScore(summary.top_score)} />
        <SummaryTile label="Promoted" value={formatMetadataDate(metadata.promoted_at)} />
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {item.source_type === 'thumbs_down_feedback' && (
          <div className="rounded-md border border-border bg-card p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Feedback</p>
            <p className="mt-2 whitespace-pre-wrap text-xs text-foreground">
              {displayMetadataValue(feedback.comment, 'Thumbs-down without comment')}
            </p>
            <p className="mt-2 text-[10px] text-muted-foreground">
              {displayMetadataValue(feedback.client_email)} · {formatMetadataDate(feedback.created_at)}
            </p>
          </div>
        )}
        {item.source_type === 'fallback_retrieval' && (
          <div className="rounded-md border border-border bg-card p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Fallback Group</p>
            <p className="mt-2 text-xs text-foreground">{displayMetadataValue(fallback.normalized_query)}</p>
            <p className="mt-2 text-[10px] text-muted-foreground">
              {displayMetadataValue(fallback.fallback_count)} events · {formatMetadataDate(fallback.first_seen_at)} to {formatMetadataDate(fallback.last_seen_at)}
            </p>
          </div>
        )}
        <div className="rounded-md border border-border bg-card p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Conversation</p>
          <p className="mt-2 text-xs text-foreground">{displayMetadataValue(conversation.thread_title, item.question)}</p>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Thread {displayMetadataValue(conversation.thread_id)} · Answer {displayMetadataValue(conversation.answer_message_id)}
          </p>
        </div>
      </div>

      {Boolean(answer.content) && (
        <div className="mt-3 rounded-md border border-border bg-card p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Captured Answer</p>
          <p className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-foreground">
            {displayMetadataValue(answer.content)}
          </p>
        </div>
      )}

      <div className="mt-3 space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Retrieval Metadata</p>
        {logs.length === 0 ? (
          <div className="rounded-md border border-border bg-card p-3 text-xs text-muted-foreground">No captured retrieval logs</div>
        ) : (
          logs.slice(0, 3).map((log, index) => {
            const sources = asRecordArray(log.sources)
            const diagnostics = asRecord(log.diagnostics)
            return (
              <div key={`${displayMetadataValue(log.id, 'log')}-${index}`} className="rounded-md border border-border bg-card p-3">
                <div className="flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
                  <span className="truncate">{displayMetadataValue(log.query)}</span>
                  <span className="flex-shrink-0">{displayMetadataValue(log.retrieval_mode)} · {formatMetadataScore(log.top_score)}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                    {displayMetadataValue(log.source_count, '0')} source{displayMetadataValue(log.source_count, '0') === '1' ? '' : 's'}
                  </span>
                  {Boolean(log.retrieval_quality) && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{displayMetadataValue(log.retrieval_quality)}</span>
                  )}
                  {Boolean(diagnostics.fallback_reason) && (
                    <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-500">
                      {displayMetadataValue(diagnostics.fallback_reason)}
                    </span>
                  )}
                  {diagnostics.web_result_count !== undefined && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                      {displayMetadataValue(diagnostics.web_result_count)} web
                    </span>
                  )}
                </div>
                {sources.length > 0 && (
                  <div className="mt-2 space-y-1.5">
                    {sources.slice(0, 3).map((source, sourceIndex) => (
                      <div key={`${displayMetadataValue(source.chunk_id, 'source')}-${sourceIndex}`} className="rounded border border-border/70 bg-muted/20 px-2 py-1.5">
                        <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                          <span className="truncate">{displayMetadataValue(source.filename, displayMetadataValue(source.document_id, 'Unknown document'))}</span>
                          <span>{formatMetadataScore(source.score)}</span>
                        </div>
                        <p className="mt-1 line-clamp-2 text-[11px] text-foreground">
                          {displayMetadataValue(source.snippet ?? source.content, 'No snippet captured')}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function EvalCaseStatusCell({ item }: { item: RagEvalCase }) {
  if (item.status === 'draft') {
    return <span className="text-amber-500">Draft</span>
  }
  return <span className={item.enabled ? 'text-green-500' : 'text-muted-foreground'}>{item.enabled ? 'Enabled' : 'Off'}</span>
}

function formatEvalCaseSource(item: RagEvalCase): string {
  if (!item.source_type || item.source_type === 'manual') return 'Manual'
  return sourceTypeLabel(item.source_type)
}

function sourceTypeLabel(sourceType?: string | null): string {
  if (sourceType === 'thumbs_down_feedback') return 'Thumbs-down'
  if (sourceType === 'fallback_retrieval') return 'Fallback-heavy'
  return sourceType || 'Manual'
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}

function displayMetadataValue(value: unknown, fallback = 'n/a'): string {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function formatMetadataScore(value: unknown): string {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(3) : 'n/a'
}

function formatMetadataDate(value: unknown): string {
  if (!value) return 'n/a'
  const date = new Date(String(value))
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString()
}

function RagSignalsPanel({
  data,
  loading,
  draftCount,
  onReviewDrafts,
}: {
  data: RagQualitySignalsResponse | null
  loading: boolean
  draftCount: number
  onReviewDrafts: () => void
}) {
  if (loading && !data) {
    return (
      <section className="rounded-lg border border-border bg-card p-8 text-center text-xs text-muted-foreground">
        <RefreshCw className="mx-auto h-5 w-5 animate-spin" />
        <p className="mt-2">Loading RAG signals...</p>
      </section>
    )
  }

  if (!data) {
    return (
      <section className="rounded-lg border border-border bg-card p-8 text-center text-xs text-muted-foreground">
        No signal data available
      </section>
    )
  }

  const flagged = data.signals.filter((signal) => signal.status !== 'ok')

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">RAG Signals</h2>
            <p className="mt-1 text-[10px] text-muted-foreground">
              Last {data.window_hours}h - {data.totals.retrieval_count ?? 0} retrievals - {flagged.length} signal{flagged.length !== 1 ? 's' : ''} flagged
            </p>
          </div>
          <div className="grid grid-cols-4 gap-4 text-right text-[10px] text-muted-foreground">
            <div>
              <p className="font-semibold uppercase tracking-wider">Feedback</p>
              <p className="mt-1 text-sm font-bold text-foreground">{data.totals.feedback_count ?? 0}</p>
            </div>
            <div>
              <p className="font-semibold uppercase tracking-wider">Fallbacks</p>
              <p className="mt-1 text-sm font-bold text-foreground">{data.totals.fallback_count ?? 0}</p>
            </div>
            <div>
              <p className="font-semibold uppercase tracking-wider">P95</p>
              <p className="mt-1 text-sm font-bold text-foreground">{formatLatency(data.totals.latency_p95_ms)}</p>
            </div>
            <button
              type="button"
              onClick={onReviewDrafts}
              className="rounded-md border border-border bg-background px-3 py-2 text-right hover:bg-muted"
            >
              <p className="font-semibold uppercase tracking-wider">Drafts</p>
              <p className="mt-1 text-sm font-bold text-foreground">{draftCount}</p>
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {data.signals.map((signal) => (
          <SignalTile key={signal.id} signal={signal} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {data.signals.map((signal) => (
          <div key={`${signal.id}-examples`} className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold text-foreground">{signal.label} Examples</h3>
              <SignalStatusPill status={signal.status} />
            </div>
            <div className="mt-3 space-y-2">
              {signal.examples.length === 0 ? (
                <div className="rounded-md border border-border bg-background p-3 text-xs text-muted-foreground">No recent examples</div>
              ) : (
                signal.examples.map((example, index) => (
                  <div key={`${signal.id}-${example.id || index}`} className="rounded-md border border-border bg-background p-3">
                    <div className="flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
                      <span className="truncate">{example.retrieval_mode || example.reason}</span>
                      <span>{example.created_at ? new Date(example.created_at).toLocaleString() : 'recent'}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs font-semibold text-foreground">{example.query || example.reason}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{example.reason}</span>
                      {example.value !== null && example.value !== undefined && (
                        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">{String(example.value)}</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function SignalTile({ signal }: { signal: RagQualitySignal }) {
  return (
    <div className={`rounded-lg border p-4 ${signalStatusClass(signal.status)}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider">{signal.label}</p>
          <p className="mt-2 text-2xl font-bold">{formatSignalPrimary(signal)}</p>
        </div>
        {signal.status === 'ok' ? (
          <CheckCircle className="h-4 w-4 flex-shrink-0" />
        ) : (
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
        )}
      </div>
      <p className="mt-3 min-h-10 text-[11px] leading-relaxed opacity-80">{signal.description}</p>
      <div className="mt-3 flex items-center justify-between text-[10px] opacity-80">
        <span>{signal.count} case{signal.count !== 1 ? 's' : ''}</span>
        <span>{formatSignalRate(signal.rate)}</span>
      </div>
    </div>
  )
}

function SignalStatusPill({ status }: { status: RagQualitySignal['status'] }) {
  const label = status === 'ok' ? 'OK' : status === 'watch' ? 'Watch' : 'Critical'
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${signalPillClass(status)}`}>
      {label}
    </span>
  )
}

function signalStatusClass(status: RagQualitySignal['status']): string {
  if (status === 'critical') return 'border-destructive/50 bg-destructive/10 text-destructive'
  if (status === 'watch') return 'border-amber-500/50 bg-amber-500/10 text-amber-500'
  return 'border-green-500/30 bg-green-500/10 text-green-500'
}

function signalPillClass(status: RagQualitySignal['status']): string {
  if (status === 'critical') return 'bg-destructive/10 text-destructive'
  if (status === 'watch') return 'bg-amber-500/10 text-amber-500'
  return 'bg-green-500/10 text-green-500'
}

function formatSignalPrimary(signal: RagQualitySignal): string {
  if (signal.id === 'completion_latency') return formatLatency(signal.value)
  return formatSignalRate(signal.rate)
}

function formatSignalRate(value: number): string {
  return `${Math.round((value || 0) * 100)}%`
}

function formatLatency(value?: number | null): string {
  if (value === null || value === undefined) return 'n/a'
  return `${Math.round(value)}ms`
}

function StatusPill({ status }: { status: string }) {
  const className = status === 'completed'
    ? 'bg-green-500/10 text-green-500'
    : status === 'failed'
      ? 'bg-destructive/10 text-destructive'
      : 'bg-amber-500/10 text-amber-500'

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${className}`}>
      {status}
    </span>
  )
}

function ScoreTile({ label, value }: { label: string; value: number }) {
  const percentage = Math.round((value || 0) * 100)
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-bold text-foreground">{percentage}%</p>
    </div>
  )
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-bold text-foreground">{value}</p>
    </div>
  )
}

function QualityPill({ active, label }: { active: boolean; label: string }) {
  const okLabel = label === 'No sources' ? 'Sources found' : `${label} OK`
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
      active ? 'bg-destructive/10 text-destructive' : 'bg-green-500/10 text-green-500'
    }`}>
      {active ? label : okLabel}
    </span>
  )
}

function QualityChunkPreview({
  source,
  expanded,
  onToggle,
}: {
  source: RagQualitySource
  expanded: boolean
  onToggle: () => void
}) {
  const text = source.content || source.snippet || 'No chunk text captured'
  const shouldTruncate = text.length > 500
  const visibleText = !shouldTruncate || expanded ? text : `${text.slice(0, 497).trimEnd()}...`

  return (
    <div className="rounded border border-border/70 bg-muted/20 px-2 py-1.5">
      <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
        <span className="truncate">{source.chunk_id || 'captured chunk'}</span>
        <span>{formatNullableScore(source.score)} · {source.retrieval_mode || 'retrieval'}</span>
      </div>
      <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-foreground">
        {visibleText}
      </p>
      {shouldTruncate && (
        <button
          type="button"
          onClick={onToggle}
          className="mt-1 text-[10px] font-semibold text-primary hover:underline"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}

function formatNullableScore(value?: number | null): string {
  return value === null || value === undefined ? 'n/a' : value.toFixed(3)
}

function formatPercent(value?: number | null): string {
  return value === null || value === undefined ? 'n/a' : `${Math.round(value * 100)}%`
}

function groupQualitySources(item: RagQualityFeedbackItem) {
  const groups = new Map<string, {
    key: string
    label: string
    sources: NonNullable<RagQualityFeedbackItem['retrieval_logs'][number]['sources']>
  }>()

  for (const log of item.retrieval_logs) {
    for (const source of log.sources || []) {
      const key = source.document_id || source.filename || 'unknown-source'
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          label: source.filename || source.document_id || 'Unknown document',
          sources: [],
        })
      }
      groups.get(key)!.sources.push(source)
    }
  }

  return Array.from(groups.values())
}
