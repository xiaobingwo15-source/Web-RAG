import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { markInteraction, markRouteReady } from '@/lib/performance'

export function ApiDocsPage() {
  const navigate = useNavigate()

  useEffect(() => {
    markRouteReady('/admin/scalar')
  }, [])

  return (
    <div className="flex h-screen flex-col bg-background">
      <div className="flex items-center gap-3 border-b border-border px-4 py-2 bg-card">
        <button
          onClick={() => {
            markInteraction('api_docs.back_to_admin')
            navigate('/admin')
          }}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Admin
        </button>
      </div>
      <iframe
        src="/scalar"
        title="API Documentation"
        className="flex-1 w-full border-0"
      />
    </div>
  )
}
