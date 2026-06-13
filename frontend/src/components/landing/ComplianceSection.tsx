import { CheckCircle2, ClipboardCheck, LockKeyhole, MessageSquareWarning, ShieldCheck } from 'lucide-react'
import outcomeStory from '@/assets/rag-outcome-story.png'

const governanceItems = [
  {
    icon: ShieldCheck,
    title: 'Tenant-aware access',
    body: 'Public widget sessions, client chat, admin review, and owner approvals stay separated by tenant and role.',
  },
  {
    icon: ClipboardCheck,
    title: 'Evaluation-ready answers',
    body: 'Admins can seed RAG eval cases, run quality checks, and inspect answer relevance, context relevance, and groundedness.',
  },
  {
    icon: MessageSquareWarning,
    title: 'Feedback review',
    body: 'Thumbs-down answers resolve back to retrieval logs, source chunks, and failure signals for targeted fixes.',
  },
  {
    icon: LockKeyhole,
    title: 'Controlled configuration',
    body: 'Provider keys, OCR limits, parser choices, embeddings, rerankers, and web fallback settings live behind admin controls.',
  },
]

export function ComplianceSection() {
  return (
    <section id="governance" className="scroll-mt-24 overflow-hidden px-6 py-20 md:px-12 md:py-24">
      <div className="mx-auto grid max-w-[1440px] grid-cols-1 gap-12 lg:grid-cols-[minmax(0,0.95fr)_minmax(420px,1.05fr)] lg:items-center">
        <div>
          <span className="mb-3 block text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Quality and governance
          </span>
          <h2 className="text-3xl font-bold leading-tight text-on-surface md:text-5xl">
            Built for answers your team can inspect and improve.
          </h2>
          <p className="mt-6 text-sm leading-7 text-on-surface-variant md:text-base">
            RAG failures are operational problems, not mysteries. Web-RAG keeps retrieval evidence, user feedback, eval cases, and admin responses close to the conversations that need review.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {governanceItems.map(({ icon: Icon, title, body }) => (
              <article key={title} className="rounded-lg border border-outline-variant bg-surface p-5 shadow-sm">
                <Icon className="mb-4 h-7 w-7 text-primary" />
                <h3 className="text-sm font-bold text-on-surface">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-on-surface-variant">{body}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="relative">
          <figure className="overflow-hidden rounded-lg border border-outline-variant bg-surface shadow-xl">
            <img
              className="h-full w-full object-cover"
              src={outcomeStory}
              alt="RAG system outcomes across support triage, sales analysis, and policy questions"
            />
          </figure>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {['Sources captured', 'Feedback linked', 'Eval cases ready'].map((item) => (
              <div key={item} className="flex items-center gap-2 rounded-sm border border-outline-variant bg-surface-container-low px-3 py-2">
                <CheckCircle2 className="h-4 w-4 text-primary" />
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-on-surface">
                  {item}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
