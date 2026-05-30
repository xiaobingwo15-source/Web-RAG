import { useState } from 'react'
import {
  Check,
  X,
  ChevronDown,
  ChevronUp,
  Loader2,
  FileText,
  Search,
  Database,
  Globe,
} from 'lucide-react'
import type { AgentAction } from '@/lib/agent-types'

/** Minimal cleanup — preserve real details, just normalize formatting. */
function cleanThoughtText(text: string): string {
  if (!text) return ''
  return text.replace(/\.{3,}$/, '...').trim()
}

/** Get an icon for the action source */
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

export function ThoughtTrace({ thoughts, actions }: ThoughtTraceProps) {
  const [expanded, setExpanded] = useState(false)

  const hasActions = actions && actions.length > 0
  const hasThoughts = thoughts && thoughts.length > 0
  if (!hasActions && !hasThoughts) return null

  // Deduplicate checklist steps to keep list clean and precise
  const checklistSteps = hasActions
    ? actions.filter((action, idx, self) =>
        self.findIndex(a => cleanThoughtText(a.content) === cleanThoughtText(action.content)) === idx
      )
    : []

  const useStructured = hasActions && actions.some(a => !!a.type)

  return (
    <div className="mb-4 space-y-3 font-sans select-none max-w-full">
      {/* 1. Checklist Timeline Panel */}
      <div className="rounded-xl bg-muted/20 border border-border/40 p-3.5 space-y-2.5 select-text font-sans shadow-sm">
        {useStructured ? (
          checklistSteps.map((action, idx) => {
            const isCompleted = action.status === 'completed'
            const isError = action.type === 'no_results' || action.content.toLowerCase().includes('not found') || action.content.toLowerCase().includes('error')
            const isActive = action.status === 'active'
            const contentPreviews = action.data?.content_previews as string[] | undefined

            return (
              <div key={action.id || idx} className="animate-in fade-in duration-200">
                <div className="flex items-start gap-2.5 text-xs text-foreground/80 leading-normal">
                  {/* Visual Status Circle Indicator */}
                  {isError ? (
                    <div className="flex-shrink-0 flex h-[18px] w-[18px] items-center justify-center rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-500 animate-in zoom-in-75 duration-200 mt-0.5">
                      <X className="h-3 w-3" />
                    </div>
                  ) : isCompleted ? (
                    <div className="flex-shrink-0 flex h-[18px] w-[18px] items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-500 animate-in zoom-in-75 duration-200 mt-0.5">
                      <Check className="h-3 w-3" />
                    </div>
                  ) : (
                    <div className="flex-shrink-0 flex h-[18px] w-[18px] items-center justify-center rounded-full bg-primary/10 border border-primary/30 text-primary mt-0.5">
                      {isActive ? (
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                      ) : (
                        <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/45" />
                      )}
                    </div>
                  )}

                  {/* Thought content */}
                  <div className="flex-1 min-w-0">
                    <span className={`font-medium ${isActive ? 'text-primary font-semibold' : 'text-foreground/80'}`}>
                      {cleanThoughtText(action.content)}
                    </span>

                    {/* Content previews — what the agent actually found */}
                    {contentPreviews && contentPreviews.length > 0 && (
                      <div className="mt-1.5 space-y-1">
                        {contentPreviews.slice(0, 3).map((preview, pi) => (
                          <div key={pi} className="flex items-start gap-1.5 text-[11px] text-foreground/55 pl-0.5">
                            <span className="flex-shrink-0 mt-0.5 text-foreground/30">#{pi + 1}</span>
                            <span className="italic leading-snug">"{preview}"</span>
                          </div>
                        ))}
                        {contentPreviews.length > 3 && (
                          <div className="text-[11px] text-foreground/40 pl-5">
                            +{contentPreviews.length - 3} more section{contentPreviews.length - 3 !== 1 ? 's' : ''}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        ) : (
          thoughts!.map((thought, i) => (
            <div key={i} className="flex items-center gap-2.5 text-xs text-foreground/80 leading-normal">
              <div className="flex-shrink-0 flex h-[18px] w-[18px] items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-500">
                <Check className="h-3 w-3" />
              </div>
              <span className="font-medium">{cleanThoughtText(thought)}</span>
            </div>
          ))
        )}
      </div>

      {/* 2. Unified Collapsible "Thought process" Card */}
      <div className="rounded-xl border border-border/40 bg-card p-3 shadow-sm select-none">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center justify-between text-xs font-semibold text-foreground/85 hover:text-foreground transition-colors select-none cursor-pointer"
        >
          <span>Thought process</span>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </button>

        {expanded && (
          <div className="mt-3 border-t border-border/40 pt-3 space-y-3 text-xs text-foreground/80 leading-relaxed font-sans select-text">
            {useStructured ? (
              actions!.map((action, idx) => {
                const contentPreviews = action.data?.content_previews as string[] | undefined
                const sql = action.data?.sql as string | undefined
                const sources = action.data?.sources as { title: string; url: string }[] | undefined

                return (
                  <div key={action.id || idx} className="animate-in fade-in duration-200 space-y-1">
                    <p className="pr-1">
                      <span className="inline-flex items-center gap-1 mr-1 text-foreground/50">
                        {sourceIcon(action.source)}
                      </span>
                      {cleanThoughtText(action.content)}
                    </p>

                    {/* Show SQL query if available */}
                    {sql && (
                      <pre className="ml-5 mt-1 p-2 rounded bg-muted/30 border border-border/30 text-[11px] font-mono text-foreground/60 overflow-x-auto whitespace-pre-wrap break-all">
                        {sql}
                      </pre>
                    )}

                    {/* Show content previews — what was found */}
                    {contentPreviews && contentPreviews.length > 0 && (
                      <div className="ml-5 mt-1.5 space-y-1.5">
                        {contentPreviews.map((preview, pi) => (
                          <div key={pi} className="flex items-start gap-1.5 text-[11px] text-foreground/55">
                            <span className="flex-shrink-0 mt-0.5 text-foreground/30">#{pi + 1}</span>
                            <span className="italic leading-snug">"{preview}"</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Show web sources */}
                    {sources && sources.length > 0 && (
                      <div className="ml-5 mt-1 space-y-0.5">
                        {sources.slice(0, 5).map((src, si) => (
                          <div key={si} className="flex items-center gap-1.5 text-[11px] text-foreground/60">
                            <Globe className="h-3 w-3 flex-shrink-0 text-foreground/40" />
                            <span className="font-medium text-foreground/70 truncate">{src.title}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })
            ) : (
              thoughts!.map((thought, i) => (
                <p key={i} className="pr-1">
                  • {cleanThoughtText(thought)}
                </p>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  )
}
