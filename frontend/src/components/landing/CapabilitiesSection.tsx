import { Bot, Database, FileSearch, Gauge, MessageSquare, Search, Settings, Shield } from 'lucide-react'

const capabilities = [
  {
    icon: FileSearch,
    title: 'Document intelligence',
    body: 'Parser selection, OCR controls, metadata extraction, duplicate detection, chunk previews, and upload recovery for large files.',
    tag: 'Ingestion',
  },
  {
    icon: Search,
    title: 'Hybrid retrieval',
    body: 'Vector search, full-text search, reciprocal ranking, reranker support, retrieval modes, and source snippets on answers.',
    tag: 'Grounding',
  },
  {
    icon: Bot,
    title: 'Agent routing',
    body: 'Supervisor routing can move between document RAG, read-only SQL analysis, web fallback, and general assistant behavior.',
    tag: 'Tools',
  },
  {
    icon: MessageSquare,
    title: 'Client chat',
    body: 'Streaming tokens, threaded conversations, image prompts, reply context, citations, and thumbs-up/down feedback.',
    tag: 'Workspace',
  },
  {
    icon: Settings,
    title: 'Admin controls',
    body: 'AI provider settings, tenant users, document status, flagged conversations, manual responses, and API docs access.',
    tag: 'Operations',
  },
  {
    icon: Gauge,
    title: 'RAG quality loop',
    body: 'Golden eval cases, eval runs, retrieval logs, groundedness flags, no-source signals, and feedback triage.',
    tag: 'Evaluation',
  },
  {
    icon: Shield,
    title: 'Tenant isolation',
    body: 'Supabase auth, tenant resolution, role redirects, owner approval, admin/client separation, and row-level policies.',
    tag: 'Security',
  },
  {
    icon: Database,
    title: 'Embeddings path',
    body: 'Gemini embeddings by default with local SentenceTransformers support for offline testing and controlled environments.',
    tag: 'Indexing',
  },
]

export function CapabilitiesSection() {
  return (
    <section id="capabilities" className="bg-[#F7FAFC] py-20 md:py-24 border-y border-outline-variant scroll-mt-24">
      <div className="px-6 md:px-12 max-w-[1440px] mx-auto">
        <div className="mb-16 text-center">
          <span className="font-semibold text-xs tracking-[0.2em] text-secondary uppercase block mb-2">
            Capabilities
          </span>
          <h2 className="text-3xl md:text-4xl font-bold text-on-surface">
            The production surfaces are already wired together.
          </h2>
        </div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
          {capabilities.map(({ icon: Icon, title, body, tag }) => (
            <article key={title} className="rounded-lg border border-outline-variant bg-white p-6 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg">
              <div className="mb-5 flex items-center justify-between gap-4">
                <Icon className="h-8 w-8 text-primary" />
                <span className="rounded-sm border border-outline-variant bg-surface-container-low px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                  {tag}
                </span>
              </div>
              <h3 className="text-lg font-bold text-on-surface">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-on-surface-variant">{body}</p>
            </article>
          ))}
        </div>

        <div className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-[#0B1B33]/10 bg-[#0B1B33] p-6 text-white">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-[#A7F3D0]">
              Public
            </span>
            <p className="mt-3 text-2xl font-bold">Landing assistant</p>
            <p className="mt-2 text-sm leading-6 text-white/70">
              Anonymous widget sessions let prospects ask about indexed knowledge without exposing the protected workspace.
            </p>
          </div>
          <div className="rounded-lg border border-outline-variant bg-white p-6">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
              Client
            </span>
            <p className="mt-3 text-2xl font-bold text-on-surface">Chat arena</p>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              Users work in threaded conversations with source previews, retrieval toggles, and streaming responses.
            </p>
          </div>
          <div className="rounded-lg border border-outline-variant bg-white p-6">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-secondary">
              Admin
            </span>
            <p className="mt-3 text-2xl font-bold text-on-surface">Control room</p>
            <p className="mt-2 text-sm leading-6 text-on-surface-variant">
              Admins manage documents, users, settings, feedback, evals, and the conversations that need human attention.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
