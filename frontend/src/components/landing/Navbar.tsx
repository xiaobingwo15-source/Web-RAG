import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'

const NAV_LINKS = [
  { label: 'Solutions', href: '#solutions' },
  { label: 'Capabilities', href: '#capabilities' },
  { label: 'Compliance', href: '#compliance' },
  { label: 'Support', href: '#contact' },
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
          ? 'bg-surface/95 backdrop-blur-sm shadow-xl border-outline-variant py-2'
          : 'bg-surface border-outline-variant/30 py-4'
        }`}
    >
      <div className="flex items-center justify-between px-6 md:px-12 w-full max-w-[1440px] mx-auto">
        <a href="#" className="font-sans text-lg md:text-xl font-bold tracking-tight text-on-surface hover:opacity-90 active:scale-95 transition-all">
          IE Industrial Electronics
        </a>

        {/* Desktop Links */}
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

        {/* Actions */}
        <div className="hidden md:flex items-center gap-4">
          <a
            href="#contact"
            className="px-4 py-2 bg-secondary text-on-secondary font-semibold text-xs rounded-sm transition-all duration-200 hover:brightness-110 active:scale-95"
          >
            Request Quote
          </a>
          <Link
            to="/login"
            className="px-4 py-2 border border-outline-variant text-on-surface font-semibold text-xs rounded-sm hover:bg-surface-variant transition-all duration-200 active:scale-95"
          >
            Portal
          </Link>
        </div>

        {/* Mobile Toggle */}
        <button
          className="text-on-surface md:hidden focus:outline-none"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="border-t border-outline-variant bg-surface/98 backdrop-blur-md px-6 py-6 md:hidden absolute left-0 right-0 top-[100%] shadow-2xl flex flex-col gap-6">
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
              className="w-full py-3 bg-secondary text-on-secondary font-semibold text-xs rounded-sm text-center"
            >
              Request Quote
            </a>
            <Link
              to="/login"
              onClick={() => setMobileOpen(false)}
              className="w-full py-3 border border-outline-variant text-on-surface font-semibold text-xs rounded-sm text-center hover:bg-surface-variant"
            >
              Portal
            </Link>
          </div>
        </div>
      )}
    </nav>
  );
}

