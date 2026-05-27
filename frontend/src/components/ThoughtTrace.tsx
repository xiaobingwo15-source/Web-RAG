import { useState } from 'react'
import { ChevronDown, ChevronRight, Brain } from 'lucide-react'

export function ThoughtTrace({ thoughts }: { thoughts: string[] }) {
  const [expanded, setExpanded] = useState(false)

  if (!thoughts || thoughts.length === 0) return null

  return (
    <div className="mb-2">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Brain className="h-3 w-3" />
        <span>Reasoning ({thoughts.length} steps)</span>
      </button>
      {expanded && (
        <div className="mt-1.5 space-y-1 border-l-2 border-muted pl-4">
          {thoughts.map((thought, i) => (
            <p key={i} className="text-xs italic text-muted-foreground">
              {thought}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
