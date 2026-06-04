import {
  Check,
  X,
  Loader2,
  FileText,
  Search,
  Database,
  Globe,
} from 'lucide-react'
import type { AgentAction } from '@/lib/agent-types'

function cleanThoughtText(text: string): string {
  if (!text) return ''
  return text.replace(/\.{3,}$/, '...').trim()
}

function sourceIcon(source: string) {
  switch (source) {
    case 'doc_rag':
      return <FileText className="h-3 w-3" />
    case 'sql':
      return <Database className="h-3 w-3" />
    case 'web_search':
      return <Globe className="h-3 w-3" />
    default:
      return <Search className="h-3 w-3" />
  }
}

interface ThoughtTraceProps {
  thoughts?: string[]
  actions?: AgentAction[]
}

const NOISY_ACTION_TYPES = new Set(['analyzing', 'routing'])

function isNoisyStatus(text: string, type?: string): boolean {
  const normalized = cleanThoughtText(text).toLowerCase()
  return (
    (type ? NOISY_ACTION_TYPES.has(type) : false) ||
    normalized.startsWith('analyzing query') ||
    normalized.startsWith('routing to:')
  )
}

function dedupeActions(actions: AgentAction[]): AgentAction[] {
  return actions.filter((action, idx, self) =>
    self.findIndex(a => cleanThoughtText(a.content) === cleanThoughtText(action.content)) === idx
  )
}

function pickPrimaryAction(actions: AgentAction[]): AgentAction | undefined {
  const deduped = dedupeActions(actions)
  const active = [...deduped].reverse().find(action => action.status === 'active')
  if (active) return active

  return (
    [...deduped].reverse().find(action => !isNoisyStatus(action.content, action.type)) ||
    deduped[deduped.length - 1]
  )
}

function pickPrimaryThought(thoughts: string[]): string | undefined {
  return (
    [...thoughts].reverse().find(thought => !isNoisyStatus(thought)) ||
    thoughts[thoughts.length - 1]
  )
}

function latestEvidenceAction(actions: AgentAction[]): AgentAction | undefined {
  return [...actions].reverse().find((action) => {
    const previews = action.data?.content_previews as string[] | undefined
    const sources = action.data?.sources as { title: string; url: string }[] | undefined
    return Boolean(action.data?.sql || previews?.length || sources?.length)
  })
}

export function ThoughtTrace({ thoughts, actions }: ThoughtTraceProps) {
  const hasActions = actions && actions.length > 0
  const hasThoughts = thoughts && thoughts.length > 0
  if (!hasActions && !hasThoughts) return null

  const primaryAction = hasActions ? pickPrimaryAction(actions!) : undefined
  const primaryThought = primaryAction ? undefined : pickPrimaryThought(thoughts || [])
  const evidenceAction = hasActions ? latestEvidenceAction(actions!) : undefined
  const evidence = evidenceAction || primaryAction
  const contentPreviews = evidence?.data?.content_previews as string[] | undefined
  const sql = evidence?.data?.sql as string | undefined
  const sources = evidence?.data?.sources as { title: string; url: string }[] | undefined
  const statusText = cleanThoughtText(primaryAction?.content || primaryThought || '')
  if (!statusText) return null

  const isActive = primaryAction?.status === 'active'
  const isError =
    primaryAction?.type === 'no_results' ||
    statusText.toLowerCase().includes('not found') ||
    statusText.toLowerCase().includes('error')

  return (
    <div className="mb-3 max-w-full rounded-lg border border-[#E9EDEF] bg-white p-3 shadow-sm select-text font-sans">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-[#667781]">
        <span>Thought process</span>
      </div>

      <div className="flex items-start gap-2.5 text-xs leading-normal text-foreground/80">
        <div
          className={`mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border ${
            isError
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-500'
              : isActive
                ? 'border-primary/30 bg-primary/10 text-primary'
                : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500'
          }`}
        >
          {isError ? (
            <X className="h-3 w-3" />
          ) : isActive ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Check className="h-3 w-3" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <p className={`font-medium ${isActive ? 'font-semibold text-primary' : 'text-foreground/80'}`}>
            {primaryAction && (
              <span className="mr-1 inline-flex align-[-2px] text-foreground/45">
                {sourceIcon(primaryAction.source)}
              </span>
            )}
            {statusText}
          </p>

          {sql && (
            <pre className="mt-2 rounded border border-border/30 bg-muted/30 p-2 font-mono text-[11px] text-foreground/60 overflow-x-auto whitespace-pre-wrap break-all">
              {sql}
            </pre>
          )}

          {contentPreviews && contentPreviews.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {contentPreviews.slice(0, 3).map((preview, idx) => (
                <div key={idx} className="flex items-start gap-1.5 text-[11px] text-foreground/55">
                  <span className="mt-0.5 shrink-0 text-foreground/30">#{idx + 1}</span>
                  <span className="line-clamp-2 italic leading-snug">"{preview}"</span>
                </div>
              ))}
              {contentPreviews.length > 3 && (
                <div className="pl-5 text-[11px] text-foreground/40">
                  +{contentPreviews.length - 3} more section{contentPreviews.length - 3 !== 1 ? 's' : ''}
                </div>
              )}
            </div>
          )}

          {sources && sources.length > 0 && (
            <div className="mt-2 space-y-0.5">
              {sources.slice(0, 3).map((src, idx) => (
                <div key={idx} className="flex items-center gap-1.5 text-[11px] text-foreground/60">
                  <Globe className="h-3 w-3 shrink-0 text-foreground/40" />
                  <span className="truncate font-medium text-foreground/70">{src.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
