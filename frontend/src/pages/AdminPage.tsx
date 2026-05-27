import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useDocuments } from '@/hooks/useDocuments'
import { useFlaggedNotifications } from '@/hooks/useFlaggedNotifications'
import { DocumentUpload } from '@/components/DocumentUpload'
import {
  getAdminConversations,
  getAdminThreadMessages,
  getAdminSettings,
  saveAdminSettings,
  getFlaggedMessages,
  submitAdminResponse,
  type AdminClient,
  type AdminMessage,
  type SystemSettings,
  type FlaggedMessage,
} from '@/lib/api'
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
  Settings,
  Eye,
  EyeOff,
  Save,
  AlertTriangle,
} from 'lucide-react'

export function AdminPage() {
  const { user, session, signOut } = useAuth()
  const navigate = useNavigate()
  const {
    documents,
    uploadDocument,
    isUploading,
    duplicateWarning,
    clearDuplicateWarning,
    uploadFailure,
    clearUploadFailure
  } = useDocuments()

  const [activeTab, setActiveTab] = useState<'conversations' | 'settings'>('conversations')
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

  // Settings State
  const [apiSettings, setApiSettings] = useState<SystemSettings>({
    GOOGLE_API_KEY: '',
    OPENROUTER_API_KEY: '',
    TAVLY_API_KEY: '',
    LANGFUSE_PUBLIC_KEY: '',
    LANGFUSE_SECRET_KEY: '',
    LANGFUSE_BASE_URL: 'https://jp.cloud.langfuse.com',
  })
  const [showKeys, setShowKeys] = useState<{ [key: string]: boolean }>({})
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsSuccess, setSettingsSuccess] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)

  const fetchConversations = useCallback(async () => {
    if (!session?.access_token) return
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

  const fetchSettings = useCallback(async () => {
    if (!session?.access_token) return
    setSettingsLoading(true)
    setSettingsError(null)
    try {
      const data = await getAdminSettings(session.access_token)
      setApiSettings({
        GOOGLE_API_KEY: data.GOOGLE_API_KEY || '',
        OPENROUTER_API_KEY: data.OPENROUTER_API_KEY || '',
        TAVLY_API_KEY: data.TAVLY_API_KEY || '',
        LANGFUSE_PUBLIC_KEY: data.LANGFUSE_PUBLIC_KEY || '',
        LANGFUSE_SECRET_KEY: data.LANGFUSE_SECRET_KEY || '',
        LANGFUSE_BASE_URL: data.LANGFUSE_BASE_URL || 'https://jp.cloud.langfuse.com',
      })
    } catch (err: any) {
      console.error('Failed to fetch admin settings:', err)
      setSettingsError(err.message || 'Failed to load system settings.')
    } finally {
      setSettingsLoading(false)
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

  useEffect(() => {
    if (activeTab === 'settings') {
      fetchSettings()
    }
  }, [activeTab, fetchSettings])

  const handleSelectThread = async (threadId: string, title: string) => {
    if (!session?.access_token) return
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

  const toggleShowKey = (key: string) => {
    setShowKeys((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!session?.access_token) return
    setSettingsSaving(true)
    setSettingsSuccess(false)
    setSettingsError(null)
    try {
      await saveAdminSettings(apiSettings, session.access_token)
      setSettingsSuccess(true)
      await fetchSettings() // Reload settings to update masked fields
      setTimeout(() => setSettingsSuccess(false), 4000)
    } catch (err: any) {
      console.error('Failed to save settings:', err)
      setSettingsError(err.message || 'Failed to save system settings.')
    } finally {
      setSettingsSaving(false)
    }
  }

  const filteredClients = flaggedFilter
    ? clients
        .filter((c) => c.threads.some((t) => flaggedMessages.some((f) => f.thread_id === t.id)))
        .map((c) => ({
          ...c,
          threads: c.threads.filter((t) => flaggedMessages.some((f) => f.thread_id === t.id)),
        }))
        .filter((c) => c.email.toLowerCase().includes(searchQuery.toLowerCase()))
    : clients.filter((c) => c.email.toLowerCase().includes(searchQuery.toLowerCase()))

  const totalThreads = clients.reduce((sum, c) => sum + c.threads.length, 0)
  const totalMessages = clients.reduce(
    (sum, c) => sum + c.threads.reduce((s, t) => s + t.message_count, 0),
    0
  )

  return (
    <div className="flex h-screen bg-background">
      {/* ── Left sidebar: Admin Controls & Knowledge Base ── */}
      <aside className="flex w-80 flex-col border-r border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3 bg-muted/10">
          <Shield className="h-5 w-5 text-primary" />
          <h2 className="text-sm font-bold text-foreground">Admin Workspace</h2>
        </div>

        {/* Workspace Tab Selector */}
        <div className="flex border-b border-border bg-muted/5 p-1.5 gap-1.5">
          <button
            onClick={() => setActiveTab('conversations')}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold transition-all ${
              activeTab === 'conversations'
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            Chats
            {flaggedCount > 0 && (
              <span className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-destructive-foreground">
                {flaggedCount > 9 ? '9+' : flaggedCount}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-semibold transition-all ${
              activeTab === 'settings'
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            }`}
          >
            <Settings className="h-3.5 w-3.5" />
            API Keys
          </button>
        </div>

        {/* Shared Knowledge Base documents section */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/5">
          <Database className="h-4 w-4 text-primary" />
          <h3 className="text-xs font-bold text-foreground">Shared Knowledge Base</h3>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          <DocumentUpload
            documents={documents}
            isUploading={isUploading}
            onUpload={uploadDocument}
            duplicateWarning={duplicateWarning}
            onDismissWarning={clearDuplicateWarning}
            uploadFailure={uploadFailure}
            onDismissFailure={clearUploadFailure}
          />
        </div>

        {/* User info */}
        <div className="border-t border-border p-4 bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 ring-2 ring-primary/30">
              <Shield className="h-4 w-4 text-primary" />
            </div>
            <div className="flex-1 truncate">
              <p className="truncate text-xs font-semibold text-primary">Admin</p>
              <p className="truncate text-[10px] text-muted-foreground">
                {user?.email ?? 'Unknown'}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Right Panel: Toggle between Chats and Settings ── */}
      {activeTab === 'conversations' ? (
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* Top bar */}
          <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-card/50">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Users className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground">Client Conversation Records</h1>
                <p className="text-[10px] text-muted-foreground">
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
      ) : (
        /* ── API Settings workspace ── */
        <main className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-6 py-3 bg-card/50">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                <Settings className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground">System API Settings</h1>
                <p className="text-[10px] text-muted-foreground">
                  Configure artificial intelligence models and analytics tracing at runtime.
                </p>
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 bg-card/10">
            <div className="mx-auto max-w-4xl space-y-6">
              <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
                <h2 className="text-sm font-bold text-foreground">Environment Credentials</h2>
                <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                  Credentials configured here override local <code className="text-primary">.env</code> values. Redacted keys (<code className="text-muted-foreground">••••••••</code>) represent existing active values. Leave them unchanged or type over to update them.
                </p>
              </div>

              {settingsLoading ? (
                <div className="flex h-64 items-center justify-center">
                  <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <form onSubmit={handleSaveSettings} className="space-y-6">
                  {settingsError && (
                    <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-xs text-destructive">
                      {settingsError}
                    </div>
                  )}
                  {settingsSuccess && (
                    <div className="rounded-lg border border-green-500/20 bg-green-500/10 p-4 text-xs text-green-400">
                      System credentials saved successfully! Hot-reload caches cleared.
                    </div>
                  )}

                  <div className="grid gap-6 md:grid-cols-2">
                    {/* Google AI Studio embeddings */}
                    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-500/10">
                          <Bot className="h-4 w-4 text-red-500" />
                        </div>
                        <div>
                          <h3 className="text-xs font-semibold text-foreground">Google AI Studio</h3>
                          <p className="text-[10px] text-muted-foreground">For vector embeddings generator</p>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-semibold text-muted-foreground">GOOGLE_API_KEY</label>
                        <div className="relative">
                          <input
                            type={showKeys['GOOGLE_API_KEY'] ? 'text' : 'password'}
                            placeholder="Enter Google Studio key"
                            value={apiSettings.GOOGLE_API_KEY}
                            onChange={(e) => setApiSettings({ ...apiSettings, GOOGLE_API_KEY: e.target.value })}
                            className="w-full rounded-md border border-border bg-input px-3 py-2 pr-10 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                          />
                          <button
                            type="button"
                            onClick={() => toggleShowKey('GOOGLE_API_KEY')}
                            className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                          >
                            {showKeys['GOOGLE_API_KEY'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-normal">
                          Configures the <code className="text-red-400">gemini-embedding-001</code> model for document vectorization.
                        </p>
                      </div>
                    </div>

                    {/* OpenRouter (Deepseek/Gemini LLM) */}
                    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/10">
                          <Shield className="h-4 w-4 text-blue-500" />
                        </div>
                        <div>
                          <h3 className="text-xs font-semibold text-foreground">OpenRouter</h3>
                          <p className="text-[10px] text-muted-foreground">For Chat & Reasoning Models</p>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-semibold text-muted-foreground">OPENROUTER_API_KEY</label>
                        <div className="relative">
                          <input
                            type={showKeys['OPENROUTER_API_KEY'] ? 'text' : 'password'}
                            placeholder="Enter OpenRouter API key"
                            value={apiSettings.OPENROUTER_API_KEY}
                            onChange={(e) => setApiSettings({ ...apiSettings, OPENROUTER_API_KEY: e.target.value })}
                            className="w-full rounded-md border border-border bg-input px-3 py-2 pr-10 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                          />
                          <button
                            type="button"
                            onClick={() => toggleShowKey('OPENROUTER_API_KEY')}
                            className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                          >
                            {showKeys['OPENROUTER_API_KEY'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-normal">
                          Used to run conversation responses, agents, OCR, and reasoning tracing.
                        </p>
                      </div>
                    </div>

                    {/* Tavly Search */}
                    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-green-500/10">
                          <Search className="h-4 w-4 text-green-500" />
                        </div>
                        <div>
                          <h3 className="text-xs font-semibold text-foreground">Tavly Web Search</h3>
                          <p className="text-[10px] text-muted-foreground">For internet grounding agents</p>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-semibold text-muted-foreground">TAVLY_API_KEY</label>
                        <div className="relative">
                          <input
                            type={showKeys['TAVLY_API_KEY'] ? 'text' : 'password'}
                            placeholder="Enter Tavly search key"
                            value={apiSettings.TAVLY_API_KEY}
                            onChange={(e) => setApiSettings({ ...apiSettings, TAVLY_API_KEY: e.target.value })}
                            className="w-full rounded-md border border-border bg-input px-3 py-2 pr-10 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                          />
                          <button
                            type="button"
                            onClick={() => toggleShowKey('TAVLY_API_KEY')}
                            className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                          >
                            {showKeys['TAVLY_API_KEY'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-normal">
                          Provides live internet fallback search when local files are insufficient.
                        </p>
                      </div>
                    </div>

                    {/* Langfuse Tracing */}
                    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4 md:col-span-2">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-500/10">
                          <RefreshCw className="h-4 w-4 text-purple-500" />
                        </div>
                        <div>
                          <h3 className="text-xs font-semibold text-foreground">Langfuse Observability</h3>
                          <p className="text-[10px] text-muted-foreground">For deep LLM telemetry and token tracking</p>
                        </div>
                      </div>

                      <div className="grid gap-4 sm:grid-cols-3">
                        <div className="space-y-1.5">
                          <label className="text-[10px] font-semibold text-muted-foreground">LANGFUSE_PUBLIC_KEY</label>
                          <input
                            type="text"
                            placeholder="pk-lf-..."
                            value={apiSettings.LANGFUSE_PUBLIC_KEY}
                            onChange={(e) => setApiSettings({ ...apiSettings, LANGFUSE_PUBLIC_KEY: e.target.value })}
                            className="w-full rounded-md border border-border bg-input px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                          />
                        </div>

                        <div className="space-y-1.5">
                          <label className="text-[10px] font-semibold text-muted-foreground">LANGFUSE_SECRET_KEY</label>
                          <div className="relative">
                            <input
                              type={showKeys['LANGFUSE_SECRET_KEY'] ? 'text' : 'password'}
                              placeholder="sk-lf-..."
                              value={apiSettings.LANGFUSE_SECRET_KEY}
                              onChange={(e) => setApiSettings({ ...apiSettings, LANGFUSE_SECRET_KEY: e.target.value })}
                              className="w-full rounded-md border border-border bg-input px-3 py-2 pr-10 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                            />
                            <button
                              type="button"
                              onClick={() => toggleShowKey('LANGFUSE_SECRET_KEY')}
                              className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                            >
                              {showKeys['LANGFUSE_SECRET_KEY'] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                            </button>
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <label className="text-[10px] font-semibold text-muted-foreground">LANGFUSE_HOST</label>
                          <input
                            type="text"
                            placeholder="https://jp.cloud.langfuse.com"
                            value={apiSettings.LANGFUSE_BASE_URL}
                            onChange={(e) => setApiSettings({ ...apiSettings, LANGFUSE_BASE_URL: e.target.value })}
                            className="w-full rounded-md border border-border bg-input px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="flex justify-end gap-3 border-t border-border pt-4">
                    <button
                      type="button"
                      onClick={fetchSettings}
                      disabled={settingsSaving}
                      className="rounded-lg border border-border px-4 py-2 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
                    >
                      Reset Changes
                    </button>
                    <button
                      type="submit"
                      disabled={settingsSaving}
                      className="flex items-center gap-1.5 rounded-lg bg-primary px-5 py-2 text-xs font-bold text-primary-foreground hover:bg-primary/95 transition-all shadow-md active:scale-[0.98] disabled:opacity-50"
                    >
                      {settingsSaving ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="h-3.5 w-3.5" />
                      )}
                      Save Settings
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </main>
      )}
    </div>
  )
}
