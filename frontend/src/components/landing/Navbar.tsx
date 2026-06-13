import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, LogIn, Menu, X } from 'lucide-react'
import { markInteraction } from '@/lib/performance'

const NAV_LINKS = [
  { label: 'Package', href: '#package' },
  { label: 'Workflow', href: '#workflow' },
  { label: 'Capabilities', href: '#capabilities' },
  { label: 'Quality', href: '#governance' },
  { label: 'Contact', href: '#contact' },
]

export function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 50)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 border-b transition-all duration-200 ${scrolled
          ? 'bg-white/95 backdrop-blur-md shadow-lg border-outline-variant py-2'
          : 'bg-white/88 backdrop-blur-md border-outline-variant/30 py-4'
        }`}
    >
      <div className="flex items-center justify-between px-6 md:px-12 w-full max-w-[1440px] mx-auto">
        <a href="#" className="font-sans text-lg md:text-xl font-bold text-on-surface hover:opacity-90 active:scale-95 transition-all">
          Web-RAG
        </a>

        <div className="hidden md:flex gap-6 items-center">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-on-surface-variant hover:text-primary transition-all duration-200"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="hidden md:flex items-center gap-4">
          <a
            href="#contact"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-on-primary font-semibold text-xs rounded-sm transition-all duration-200 hover:bg-primary-container active:scale-95"
          >
            <CalendarDays className="h-4 w-4" />
            Plan Rollout
          </a>
          <Link
            to="/login"
            onClick={() => markInteraction('nav.portal')}
            className="inline-flex items-center gap-2 px-4 py-2 border border-outline-variant text-on-surface font-semibold text-xs rounded-sm hover:bg-surface-container-low transition-all duration-200 active:scale-95"
          >
            <LogIn className="h-4 w-4" />
            Portal
          </Link>
        </div>

        <button
          className="text-on-surface md:hidden focus:outline-none"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle navigation"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-outline-variant bg-white/98 backdrop-blur-md px-6 py-6 md:hidden absolute left-0 right-0 top-[100%] shadow-2xl flex flex-col gap-6">
          <div className="flex flex-col gap-4">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className="text-sm font-medium text-on-surface-variant hover:text-primary transition-colors py-1"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="flex flex-col gap-3 pt-4 border-t border-outline-variant">
            <a
              href="#contact"
              onClick={() => setMobileOpen(false)}
              className="inline-flex w-full items-center justify-center gap-2 py-3 bg-primary text-on-primary font-semibold text-xs rounded-sm text-center"
            >
              <CalendarDays className="h-4 w-4" />
              Plan Rollout
            </a>
            <Link
              to="/login"
              onClick={() => {
                markInteraction('nav.portal')
                setMobileOpen(false)
              }}
              className="inline-flex w-full items-center justify-center gap-2 py-3 border border-outline-variant text-on-surface font-semibold text-xs rounded-sm text-center hover:bg-surface-container-low"
            >
              <LogIn className="h-4 w-4" />
              Portal
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}
