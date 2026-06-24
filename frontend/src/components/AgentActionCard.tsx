import {
  Brain,
  GitBranch,
  Search,
  Code,
  Play,
  BookOpen,
  Sparkles,
  AlertCircle,
  Loader2,
} from 'lucide-react'
import type { AgentAction, ActionType, ActionSource } from '@/lib/agent-types'

const ACTION_ICONS: Record<ActionType, typeof Brain> = {
  analyzing: Brain,
  routing: GitBranch,
  searching: Search,
  generating_sql: Code,
  executing_sql: Play,
  reading: BookOpen,
  synthesizing: Sparkles,
  no_results: AlertCircle,
  clarifying: Search,
}

const SOURCE_LABELS: Record<ActionSource, string> = {
  supervisor: 'Supervisor',
  doc_rag: 'Knowledge Base',
  web_search: 'Web Search',
  sql: 'Database',
}

const SOURCE_COLORS: Record<ActionSource, string> = {
  supervisor: 'border-l-blue-400',
  doc_rag: 'border-l-emerald-400',
  web_search: 'border-l-amber-400',
  sql: 'border-l-purple-400',
}

function str(val: unknown): string {
  return val != null ? String(val) : ''
}

function has(val: unknown): boolean {
  return val != null && val !== ''
}

function ActionDetails({ action }: { action: AgentAction }) {
  const { type, source, data } = action

  if (type === 'searching' && source === 'doc_rag') {
    return (
      <div className="mt-1 space-y-0.5">
        {has(data.query) && <DetailRow label="Query" value={str(data.query)} />}
        {has(data.mode) && <DetailRow label="Mode" value={str(data.mode)} />}
      </div>
    )
  }

  if (type === 'searching' && source === 'web_search') {
    return (
      <div className="mt-1">
        {has(data.query) && <DetailRow label="Query" value={str(data.query)} />}
      </div>
    )
  }

  if (type === 'synthesizing' && source === 'doc_rag') {
    return (
      <div className="mt-1 space-y-0.5">
        {data.chunk_count != null && <DetailRow label="Chunks" value={`${data.chunk_count} relevant passages`} />}
        {has(data.mode) && <DetailRow label="Mode" value={str(data.mode)} />}
      </div>
    )
  }

  if (type === 'synthesizing' && source === 'web_search') {
    const sources = data.sources as Array<{ title: string; url: string }> | undefined
    return (
      <div className="mt-1 space-y-0.5">
        {data.result_count != null && <DetailRow label="Results" value={`${data.result_count} sources found`} />}
        {sources && sources.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {sources.slice(0, 3).map((s, i) => (
              <span key={i} className="inline-block rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground truncate max-w-[180px]">
                {s.title}
              </span>
            ))}
            {sources.length > 3 && (
              <span className="text-[10px] text-muted-foreground">+{sources.length - 3} more</span>
            )}
          </div>
        )}
      </div>
    )
  }

  if (type === 'routing') {
    return (
      <div className="mt-1">
        {has(data.route) && <DetailRow label="Route" value={str(data.route)} />}
      </div>
    )
  }

  if (type === 'analyzing' && source === 'sql') {
    return (
      <div className="mt-1">
        {has(data.question) && <DetailRow label="Question" value={str(data.question)} />}
      </div>
    )
  }

  if ((type === 'executing_sql' || type === 'generating_sql') && has(data.sql)) {
    const sql = str(data.sql)
    return (
      <div className="mt-1">
        <DetailRow label="SQL" value={sql.length > 80 ? sql.slice(0, 80) + '...' : sql} />
      </div>
    )
  }

  if (type === 'reading' && source === 'sql' && data.row_count != null) {
    return (
      <div className="mt-1">
        <DetailRow label="Rows" value={`${data.row_count} returned`} />
      </div>
    )
  }

  if (type === 'no_results' && has(data.error)) {
    return (
      <div className="mt-1">
        <DetailRow label="Error" value={str(data.error)} />
      </div>
    )
  }

  if (has(data.query)) {
    return (
      <div className="mt-1">
        <DetailRow label="Query" value={str(data.query)} />
      </div>
    )
  }

  return null
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5 text-[11px]">
      <span className="font-medium text-muted-foreground">{label}:</span>
      <span className="text-foreground/70 truncate">{value}</span>
    </div>
  )
}

export function AgentActionCard({ action }: { action: AgentAction | null }) {
  if (!action) return null

  const Icon = ACTION_ICONS[action.type] || Brain
  const sourceLabel = SOURCE_LABELS[action.source] || action.source
  const borderColor = SOURCE_COLORS[action.source] || 'border-l-primary'

  return (
    <div
      className={`mx-auto max-w-3xl rounded-lg border border-l-2 ${borderColor} bg-card/50 px-4 py-3 shadow-sm backdrop-blur-sm`}
    >
      <div className="flex items-center gap-2.5">
        <div className="relative flex-shrink-0">
          <Icon className="h-4 w-4 text-foreground/80" />
          <Loader2 className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 animate-spin text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground">{action.content}</span>
            <span className="flex-shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {sourceLabel}
            </span>
          </div>
          <ActionDetails action={action} />
        </div>
      </div>
    </div>
  )
}
