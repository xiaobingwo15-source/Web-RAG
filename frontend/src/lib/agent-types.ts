export type ActionType =
  | "analyzing"
  | "routing"
  | "searching"
  | "generating_sql"
  | "executing_sql"
  | "reading"
  | "synthesizing"
  | "no_results"
  | "clarifying"

export type ActionSource = "supervisor" | "doc_rag" | "web_search" | "sql"

export interface AgentAction {
  id: string
  type: ActionType
  source: ActionSource
  content: string
  data: Record<string, unknown>
  timestamp: number
  status: "active" | "completed"
}
