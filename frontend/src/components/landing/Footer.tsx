import { ArrowRight, CalendarDays, CheckCircle2, LogIn, MessageCircleQuestion } from 'lucide-react'
import { Link } from 'react-router-dom'
import { markInteraction } from '@/lib/performance'

const footerLinks = [
  { label: 'Package', href: '#package' },
  { label: 'Workflow', href: '#workflow' },
  { label: 'Capabilities', href: '#capabilities' },
  { label: 'Quality', href: '#governance' },
]

const readinessItems = [
  'Source inventory',
  'Primary use cases',
  'Tenant roles',
  'Evaluation questions',
]

export function Footer() {
  return (
    <footer id="contact" className="mt-16 border-t border-outline-variant bg-[#0B1B33] text-white">
      <div className="mx-auto grid w-full max-w-[1440px] grid-cols-1 gap-10 px-6 py-14 md:px-12 lg:grid-cols-[minmax(0,0.95fr)_minmax(320px,0.55fr)] lg:items-center">
        <div>
          <span className="mb-3 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#A7F3D0]">
            <CalendarDays className="h-4 w-4" />
            Implementation next step
          </span>
          <h2 className="max-w-3xl text-3xl font-bold leading-tight md:text-5xl">
            Ready to turn private knowledge into cited answers?
          </h2>
          <p className="mt-5 max-w-2xl text-sm leading-7 text-white/70 md:text-base">
            Start with one high-value workflow, the source files behind it, and the success criteria your team will use to trust the answers.
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <a
              href="#package"
              className="inline-flex items-center justify-center gap-2 rounded-sm bg-primary px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-on-primary transition-all hover:bg-primary-container active:scale-95"
            >
              Review Package
              <ArrowRight className="h-4 w-4" />
            </a>
            <Link
              to="/login"
              onClick={() => markInteraction('nav.portal')}
              className="inline-flex items-center justify-center gap-2 rounded-sm border border-white/20 px-5 py-3 text-xs font-semibold uppercase tracking-[0.14em] text-white transition-all hover:bg-white/10 active:scale-95"
            >
              <LogIn className="h-4 w-4" />
              Portal
            </Link>
          </div>
        </div>

        <div className="rounded-lg border border-white/12 bg-white/7 p-6">
          <div className="flex items-start gap-3">
            <MessageCircleQuestion className="mt-0.5 h-6 w-6 text-[#F7B267]" />
            <div>
              <h3 className="text-base font-bold">Bring to discovery</h3>
              <p className="mt-2 text-sm leading-6 text-white/65">
                The package scopes fastest when your first use case and source inventory are clear.
              </p>
            </div>
          </div>
          <div className="mt-5 grid gap-3">
            {readinessItems.map((item) => (
              <div key={item} className="flex items-center gap-2 rounded-sm border border-white/10 bg-white/6 px-3 py-2">
                <CheckCircle2 className="h-4 w-4 text-[#A7F3D0]" />
                <span className="text-xs font-semibold uppercase tracking-[0.1em] text-white/82">
                  {item}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto grid w-full max-w-[1440px] grid-cols-1 gap-6 border-t border-white/10 px-6 py-8 md:grid-cols-[minmax(0,1fr)_auto] md:px-12">
        <div>
          <div className="text-sm font-bold">Web-RAG</div>
          <p className="mt-2 max-w-xl text-xs leading-6 text-white/55">
            A production RAG package with ingestion, retrieval, chat, widget access, admin controls, and quality review loops.
          </p>
        </div>
        <nav className="flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold uppercase tracking-[0.12em] text-white/65">
          {footerLinks.map((link) => (
            <a key={link.href} href={link.href} className="transition-colors hover:text-[#A7F3D0]">
              {link.label}
            </a>
          ))}
        </nav>
      </div>

      <div className="border-t border-white/10 px-6 py-5 text-center">
        <p className="text-xs text-white/45">
          Copyright 2026 Web-RAG. All rights reserved.
        </p>
      </div>
    </footer>
  )
}
