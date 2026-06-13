import { ArrowRight, CalendarDays, CheckCircle2, Database, FileText, ShieldCheck } from 'lucide-react'
import heroStory from '@/assets/rag-hero-story.png'

const proofPoints = [
  { icon: FileText, label: 'Documents', value: 'PDF, Markdown, TXT, CSV' },
  { icon: Database, label: 'Data', value: 'Hybrid retrieval and SQL tools' },
  { icon: ShieldCheck, label: 'Controls', value: 'Tenants, roles, approvals' },
  { icon: CheckCircle2, label: 'Quality', value: 'Citations, evals, feedback' },
]

export function HeroSection() {
  return (
    <header className="relative overflow-hidden bg-[#071427] pt-20 md:pt-24">
      <div className="absolute inset-0 z-0">
        <img
          className="h-full w-full object-cover opacity-50"
          src={heroStory}
          alt="Documents, database, chat answers, and guardrails connected inside a RAG system"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#071427] via-[#071427]/88 to-[#071427]/35"></div>
        <div
          className="absolute inset-0 opacity-[0.14]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.22) 1px, transparent 1px)',
            backgroundSize: '56px 56px',
          }}
        ></div>
      </div>

      <div className="relative z-10 mx-auto flex min-h-[68vh] w-full max-w-[1440px] items-center px-6 pb-10 pt-6 md:min-h-[74vh] md:px-12 md:pb-20 md:pt-8">
        <div className="max-w-3xl">
          <span className="mb-4 inline-flex items-center gap-2 rounded-sm border border-white/20 bg-white/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#A7F3D0] backdrop-blur-md">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Private AI knowledge system
          </span>
          <h1 className="text-3xl font-bold leading-[1.04] text-white sm:text-4xl md:text-6xl">
            Web-RAG RAG System Package
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-white/80 md:mt-6 md:text-xl md:leading-8">
            Turn company documents, spreadsheets, and operational data into cited AI answers with streaming chat, source evidence, admin review, and deployment guardrails already built in.
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row md:mt-8 md:gap-4">
            <a
              href="#contact"
              className="flex items-center justify-center gap-2 rounded-sm bg-primary px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-on-primary transition-all duration-200 hover:bg-primary-container active:scale-95 md:px-6 md:py-4"
            >
              <CalendarDays className="h-4 w-4" />
              Plan Implementation
            </a>
            <a
              href="#package"
              className="flex items-center justify-center gap-2 rounded-sm border border-white/25 bg-white/8 px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-white backdrop-blur-md transition-all duration-200 hover:bg-white/14 active:scale-95 md:px-6 md:py-4"
            >
              See Package
              <ArrowRight className="h-4 w-4" />
            </a>
          </div>

          <div className="mt-8 grid max-w-4xl grid-cols-2 gap-x-3 gap-y-4 border-y border-white/14 py-4 sm:grid-cols-2 md:mt-12 md:gap-3 md:py-5 lg:grid-cols-4">
            {proofPoints.map(({ icon: Icon, label, value }) => (
              <div key={label} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
                <Icon className="mt-0.5 h-5 w-5 text-[#F7B267]" />
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-white">{label}</p>
                  <p className="mt-1 text-sm leading-5 text-white/65">{value}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </header>
  )
}
