import { CheckCircle2, ClipboardCheck, CloudUpload, Database, FileText, MessageSquareText, SearchCheck } from 'lucide-react'
import workflowStory from '@/assets/rag-workflow-story.png'

const deliverables = [
  {
    icon: CloudUpload,
    title: 'Source ingestion',
    body: 'Upload and process PDFs, Markdown, TXT, CSV, spreadsheets, and OCR-heavy files with duplicate checks and resilient chunked uploads.',
  },
  {
    icon: SearchCheck,
    title: 'Grounded retrieval',
    body: 'Hybrid vector and full-text search, reranking, source snippets, and retrieval modes tuned for document-heavy workflows.',
  },
  {
    icon: MessageSquareText,
    title: 'Chat workspace',
    body: 'Threaded streaming chat, RAG toggle, image-aware prompts, tool traces, citations, and feedback built into the client experience.',
  },
  {
    icon: Database,
    title: 'Admin operations',
    body: 'Tenant-aware Supabase auth, role routing, document status tracking, AI settings, conversations, eval cases, and quality signals.',
  },
]

const workflow = [
  'Map source inventory and access model',
  'Ingest files with parsing, OCR, metadata, and embeddings',
  'Retrieve with hybrid search, reranking, and source evidence',
  'Improve with eval cases, feedback review, and retrieval diagnostics',
]

export function ServicesSection() {
  return (
    <section id="package" className="scroll-mt-24 px-6 py-20 md:px-12 md:py-24">
      <div className="mx-auto max-w-[1440px]">
        <div className="mb-12 grid gap-6 md:grid-cols-[minmax(0,0.78fr)_minmax(320px,0.42fr)] md:items-end">
          <div>
            <span className="mb-3 block text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Package
            </span>
            <h2 className="max-w-3xl text-3xl font-bold leading-tight text-on-surface md:text-5xl">
              A deployed RAG application, not a starter template.
            </h2>
          </div>
          <p className="text-sm leading-7 text-on-surface-variant md:text-base">
            Web-RAG packages the production pieces teams usually have to assemble separately: ingestion, retrieval, chat, admin control, evaluation, and a public assistant widget.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-4">
          {deliverables.map(({ icon: Icon, title, body }) => (
            <article key={title} className="rounded-lg border border-outline-variant bg-surface p-6 shadow-sm">
              <Icon className="mb-5 h-8 w-8 text-primary" />
              <h3 className="text-lg font-bold text-on-surface">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-on-surface-variant">{body}</p>
            </article>
          ))}
        </div>

        <div id="workflow" className="scroll-mt-24 pt-16">
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.72fr)] lg:items-center">
            <figure className="overflow-hidden rounded-lg border border-outline-variant bg-surface shadow-xl">
              <img
                className="h-full w-full object-cover"
                src={workflowStory}
                alt="RAG workflow from source ingestion through retrieval, answers, and deployment handoff"
              />
            </figure>

            <div>
              <span className="mb-3 block text-xs font-semibold uppercase tracking-[0.2em] text-secondary">
                Workflow
              </span>
              <h3 className="text-2xl font-bold leading-tight text-on-surface md:text-4xl">
                From scattered knowledge to answerable systems.
              </h3>
              <div className="mt-7 grid gap-3">
                {workflow.map((item, index) => (
                  <div key={item} className="grid grid-cols-[44px_minmax(0,1fr)] gap-4 rounded-lg border border-outline-variant bg-surface-container-low p-4">
                    <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-[#0B1B33] text-sm font-bold text-white">
                      {index + 1}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        {index === 0 ? <FileText className="h-4 w-4 text-primary" /> : <ClipboardCheck className="h-4 w-4 text-primary" />}
                        <p className="text-sm font-semibold text-on-surface">{item}</p>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-on-surface-variant">
                        {index === 0
                          ? 'Discovery keeps scope tied to real documents, data sources, users, and success metrics.'
                          : 'Each stage leaves observable status, source evidence, or admin review data behind.'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-6 flex items-start gap-3 rounded-lg border border-primary/20 bg-[#ECFDF5] p-4">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <p className="text-sm leading-6 text-[#115E59]">
                  The existing app structure remains intact: public landing page, protected chat workspace, admin dashboard, owner approval screen, and embedded anonymous assistant.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
