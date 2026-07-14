import { useState } from 'react'
import type { ChatMessage as ChatMessageType, ChatReplyTarget } from '@/hooks/useChat'
import type { RetrievalSource } from '@/lib/api'
import { ThoughtTrace } from '@/components/ThoughtTrace'
import { BookOpen, Shield, ThumbsUp, ThumbsDown, Reply, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface ChatMessageProps {
  message: ChatMessageType
  messageId?: string
  feedback?: 1 | -1 | null
  onFeedback?: (messageId: string, rating: 1 | -1, comment?: string) => Promise<void>
  onReply?: (target: ChatReplyTarget) => void
  onSourceFollowUp?: (prompt: string) => void
}

const FEEDBACK_REASONS = ['Missing source', 'Wrong fact', 'Outdated', 'Hard to follow']

function replyAuthor(role: ChatMessageType['replyToRole']) {
  if (role === 'user') return 'You'
  if (role === 'assistant') return 'Assistant'
  return 'Message'
}

function formatMessageTime(createdAt?: string) {
  if (!createdAt) return '--:--'
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return '--:--'
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ChatMessage({ message, messageId, feedback, onFeedback, onReply, onSourceFollowUp }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const normalizedFeedback = feedback ?? null
  const [optimisticFeedback, setOptimisticFeedback] = useState<{ messageId?: string; value: 1 | -1 | null }>({ value: null })
  const [selectedSource, setSelectedSource] = useState<RetrievalSource | null>(null)
  const [feedbackDialogOpen, setFeedbackDialogOpen] = useState(false)
  const [feedbackReasons, setFeedbackReasons] = useState<string[]>([])
  const [feedbackComment, setFeedbackComment] = useState('')
  const [feedbackSubmission, setFeedbackSubmission] = useState<{
    messageId?: string
    pending: boolean
    error: string | null
  }>({ pending: false, error: null })
  const canReply = Boolean(message.content && messageId && onReply)
  const displayedFeedback = optimisticFeedback.messageId === messageId ? optimisticFeedback.value : normalizedFeedback
  const feedbackPending = feedbackSubmission.messageId === messageId && feedbackSubmission.pending
  const feedbackError = feedbackSubmission.messageId === messageId ? feedbackSubmission.error : null

  const persistFeedback = async (rating: 1 | -1, comment?: string) => {
    if (!messageId || !onFeedback || feedbackPending) return false
    setOptimisticFeedback({ messageId, value: rating })
    setFeedbackSubmission({ messageId, pending: true, error: null })
    try {
      await onFeedback(messageId, rating, comment)
      setFeedbackSubmission({ messageId, pending: false, error: null })
      return true
    } catch (error) {
      console.error('Failed to submit feedback:', error)
      setOptimisticFeedback({ messageId, value: normalizedFeedback })
      setFeedbackSubmission({
        messageId,
        pending: false,
        error: 'Feedback could not be saved. Please try again.',
      })
      return false
    }
  }

  const handleFeedback = async (rating: 1 | -1) => {
    if (feedbackPending || displayedFeedback === rating) return
    if (rating === -1 && displayedFeedback !== -1) {
      setFeedbackSubmission({ messageId, pending: false, error: null })
      setFeedbackDialogOpen(true)
      return
    }
    await persistFeedback(rating)
  }

  const toggleFeedbackReason = (reason: string) => {
    setFeedbackReasons((prev) => prev.includes(reason)
      ? prev.filter((item) => item !== reason)
      : [...prev, reason])
  }

  const submitNegativeFeedback = async () => {
    if (!messageId || !onFeedback) return
    const detail = [
      ...feedbackReasons,
      feedbackComment.trim(),
    ].filter(Boolean).join('; ')
    const saved = await persistFeedback(-1, detail || undefined)
    if (saved) {
      setFeedbackDialogOpen(false)
      setFeedbackReasons([])
      setFeedbackComment('')
    }
  }

  const timestamp = formatMessageTime(message.created_at)

  const handleReply = () => {
    if (!messageId || !message.content || !onReply) return
    onReply({ id: messageId, content: message.content, role: message.role })
  }

  return (
    <div className={`group flex ${isUser ? 'justify-end' : 'justify-start'} mb-1`}>
      <div className={`flex max-w-[86%] items-center gap-1.5 sm:max-w-[72%] ${isUser ? 'flex-row-reverse' : ''}`}>
        <div className="min-w-0">
        {/* Thought trace (assistant only) */}
        {!isUser && ((message.thoughts && message.thoughts.length > 0) || (message.actions && message.actions.length > 0)) && (
          <ThoughtTrace thoughts={message.thoughts} actions={message.actions} />
        )}

        {/* Bubble */}
        <div
          className={`relative rounded-lg px-2.5 py-1.5 shadow-sm ${
            isUser
              ? 'bg-bubble-out text-bubble-out-text'
              : 'bg-bubble-in text-bubble-in-text'
          }`}
        >
          {/* Reply-to preview */}
          {message.replyToContent && (
            <div
              className={`mb-1.5 overflow-hidden rounded-md border-l-4 border-[#00A884] px-2.5 py-1.5 ${
                isUser ? 'bg-white/65' : 'bg-[#F0F2F5]'
              }`}
            >
              <p className="text-[11px] font-semibold leading-tight text-[#008069]">
                Replying to {replyAuthor(message.replyToRole)}
              </p>
              <p className="mt-0.5 line-clamp-2 break-words text-xs leading-snug text-[#54656F]">
                {message.replyToContent}
              </p>
            </div>
          )}

          {/* Images */}
          {isUser && message.images && message.images.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-1.5">
              {message.images.map((src, idx) => (
                <img
                  key={idx}
                  src={src}
                  alt={`Pasted image ${idx + 1}`}
                  className="max-w-[200px] max-h-[200px] rounded-md object-contain"
                />
              ))}
            </div>
          )}

          {/* Content */}
          {message.content && (
            isUser ? (
              <p className="whitespace-pre-wrap text-[14.2px] leading-[1.35]">{message.content}</p>
            ) : (
              <div className="chat-markdown text-[14.2px]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              </div>
            )
          )}

          {/* Timestamp (inside bubble, bottom-right) */}
          <span className={`block text-right text-[11px] mt-0.5 ${isUser ? 'text-[#667781]' : 'text-[#667781]'}`}>
            {timestamp}
          </span>
        </div>

        {/* Admin response */}
        {!isUser && message.adminResponse && (
          <div className="mt-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1">
              <Shield className="h-3 w-3 text-amber-600" />
              <span className="text-[11px] font-semibold text-amber-700">Admin Response</span>
            </div>
            <p className="whitespace-pre-wrap text-[13px] text-[#111B21]">
              {message.adminResponse}
            </p>
          </div>
        )}

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-1.5 rounded-lg bg-white border border-[#E9EDEF] px-3 py-2">
            <div className="flex items-center gap-1.5 mb-1.5">
              <BookOpen className="h-3 w-3 text-[#00A884]" />
              <span className="text-[11px] font-semibold text-[#111B21]">Sources</span>
            </div>
            <div className="space-y-1.5">
              {message.sources.slice(0, 5).map((source, index) => (
                <button
                  key={`${source.chunk_id}-${index}`}
                  onClick={() => setSelectedSource(source)}
                  className="block w-full rounded bg-[#F5F6F6] px-2.5 py-1.5 text-left transition hover:bg-[#EEF1F1]"
                >
                  <div className="flex items-center justify-between gap-2 text-[11px]">
                    <span className="truncate font-medium text-[#111B21]">
                      {source.filename || `Document ${(source.document_id ?? '').slice(0, 8) || 'Unknown'}`}
                    </span>
                    <span className="shrink-0 text-[#667781]">
                      {source.retrieval_mode} · {(source.score ?? 0).toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-0.5 line-clamp-2 text-[12px] text-[#667781]">
                    {source.snippet}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Feedback buttons (assistant only) */}
        {!isUser && message.content && messageId && (
          <div className="mt-0.5 flex items-center gap-0.5">
            <button
              onClick={() => handleFeedback(1)}
              disabled={feedbackPending}
              className={`rounded p-1 transition-colors cursor-pointer ${
                displayedFeedback === 1
                  ? 'text-[#00A884] bg-[#00A884]/10'
                  : 'text-[#8696A0] hover:text-[#00A884] hover:bg-[#00A884]/5'
              } disabled:cursor-not-allowed disabled:opacity-50`}
              title="Good response"
              aria-label="Good response"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => handleFeedback(-1)}
              disabled={feedbackPending}
              className={`rounded p-1 transition-colors cursor-pointer ${
                displayedFeedback === -1
                  ? 'text-[#EF4444] bg-[#EF4444]/10'
                  : 'text-[#8696A0] hover:text-[#EF4444] hover:bg-[#EF4444]/5'
              } disabled:cursor-not-allowed disabled:opacity-50`}
              title="Poor response"
              aria-label="Poor response"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        {!feedbackDialogOpen && feedbackError && (
          <p className="mt-1 text-[11px] text-[#B91C1C]" role="alert">{feedbackError}</p>
        )}
        </div>

        {canReply && (
          <button
            onClick={handleReply}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/90 text-[#54656F] shadow-sm transition hover:bg-white hover:text-[#00A884] focus:outline-none focus:ring-2 focus:ring-[#00A884]/30 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 cursor-pointer"
            title="Reply"
            aria-label="Reply to this message"
          >
            <Reply className="h-4 w-4" />
          </button>
        )}
      </div>

      {selectedSource && (
        <SourceInspectorModal
          source={selectedSource}
          onClose={() => setSelectedSource(null)}
          onFollowUp={onSourceFollowUp}
        />
      )}

      {feedbackDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
          onClick={() => {
            if (!feedbackPending) setFeedbackDialogOpen(false)
          }}
        >
          <div className="w-full max-w-sm rounded-lg bg-white p-4 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-[#111B21]">What went wrong?</h3>
              <button
                onClick={() => setFeedbackDialogOpen(false)}
                disabled={feedbackPending}
                className="rounded p-1 text-[#667781] hover:bg-[#F0F2F5] disabled:cursor-not-allowed disabled:opacity-50"
                aria-label="Close feedback"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {FEEDBACK_REASONS.map((reason) => (
                <button
                  key={reason}
                  onClick={() => toggleFeedbackReason(reason)}
                  disabled={feedbackPending}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                    feedbackReasons.includes(reason)
                      ? 'border-[#EF4444] bg-[#EF4444]/10 text-[#EF4444]'
                      : 'border-[#E9EDEF] text-[#54656F] hover:bg-[#F5F6F6]'
                  }`}
                >
                  {reason}
                </button>
              ))}
            </div>
            <textarea
              value={feedbackComment}
              onChange={(event) => setFeedbackComment(event.target.value)}
              disabled={feedbackPending}
              rows={3}
              placeholder="Add details for the admin"
              className="mt-3 w-full resize-none rounded-md border border-[#E9EDEF] px-3 py-2 text-sm text-[#111B21] placeholder:text-[#8696A0] focus:outline-none focus:ring-2 focus:ring-[#00A884]/30"
            />
            {feedbackError && (
              <p className="mt-2 text-xs text-[#B91C1C]" role="alert">{feedbackError}</p>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <button
                onClick={() => setFeedbackDialogOpen(false)}
                disabled={feedbackPending}
                className="rounded-md px-3 py-1.5 text-xs font-semibold text-[#54656F] hover:bg-[#F0F2F5] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={submitNegativeFeedback}
                disabled={feedbackPending}
                className="rounded-md bg-[#EF4444] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#DC2626] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {feedbackPending ? 'Submitting...' : 'Submit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function SourceInspectorModal({
  source,
  onClose,
  onFollowUp,
}: {
  source: RetrievalSource
  onClose: () => void
  onFollowUp?: (prompt: string) => void
}) {
  const breadcrumb = Array.isArray(source.breadcrumb_path)
    ? source.breadcrumb_path.join(' / ')
    : source.breadcrumb_path
  const pageLabel = source.page_start && source.page_end && source.page_start !== source.page_end
    ? `Pages ${source.page_start}-${source.page_end}`
    : source.page_start
      ? `Page ${source.page_start}`
      : null
  const sourceName = source.filename || `Document ${(source.document_id ?? '').slice(0, 8) || 'Unknown'}`

  const makeFollowUp = (kind: 'focus' | 'support') => {
    const section = source.heading ? ` section "${source.heading}"` : ''
    return kind === 'focus'
      ? `Ask a follow-up using ${sourceName}${section}: `
      : `Explain how this source supports the previous answer: ${sourceName}${section}`
  }

  const handleFollowUp = (kind: 'focus' | 'support') => {
    onFollowUp?.(makeFollowUp(kind))
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4" onClick={onClose}>
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 border-b border-[#E9EDEF] px-5 py-4">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-[#111B21]">{sourceName}</h3>
            <p className="mt-1 text-xs text-[#667781]">
              {source.retrieval_mode} · {source.score_family || 'score'} · {(source.score ?? 0).toFixed(3)}
            </p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-[#667781] hover:bg-[#F0F2F5]" aria-label="Close source details">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <SourceMeta label="Chunk" value={source.chunk_id} />
            <SourceMeta label="Document" value={source.document_id} />
            <SourceMeta label="Heading" value={source.heading || undefined} />
            <SourceMeta label="Location" value={pageLabel || undefined} />
            <SourceMeta label="Type" value={source.structural_type || undefined} />
            <SourceMeta label="Table" value={source.table_id || undefined} />
          </div>
          {breadcrumb && (
            <div className="mt-3 rounded-md border border-[#E9EDEF] bg-[#F5F6F6] px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#667781]">Breadcrumb</p>
              <p className="mt-1 text-xs text-[#111B21]">{breadcrumb}</p>
            </div>
          )}
          <div className="mt-3 rounded-md border border-[#E9EDEF] bg-[#F5F6F6] px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-[#667781]">Snippet</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[#111B21]">{source.snippet || 'No snippet captured'}</p>
          </div>
        </div>
        {onFollowUp && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-[#E9EDEF] px-5 py-3">
            <button
              onClick={() => handleFollowUp('support')}
              className="rounded-md border border-[#D8E8E4] px-3 py-1.5 text-xs font-semibold text-[#008069] hover:bg-[#F0F2F5]"
            >
              Explain evidence
            </button>
            <button
              onClick={() => handleFollowUp('focus')}
              className="rounded-md bg-[#00A884] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#008F72]"
            >
              Ask follow-up
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function SourceMeta({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="rounded-md border border-[#E9EDEF] bg-[#F5F6F6] px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-[#667781]">{label}</p>
      <p className="mt-1 truncate text-xs text-[#111B21]">{value || 'n/a'}</p>
    </div>
  )
}
