import { Share2, Mail, Globe } from 'lucide-react'

export function Footer() {
  return (
    <footer className="bg-surface-container border-t border-outline-variant mt-24">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 w-full py-16 px-6 md:px-12 max-w-[1440px] mx-auto">
        <div>
          <div className="font-semibold text-xs tracking-[0.2em] text-on-surface uppercase mb-4">
            IE Industrial Technology
          </div>
          <p className="text-on-surface-variant text-sm leading-relaxed max-w-sm mb-6">
            A global leader in high-reliability PCB manufacturing and component engineering for industrial vertical markets.
          </p>
          <div className="flex gap-4">
            <a
              href="#"
              aria-label="Share"
              className="text-on-surface-variant hover:text-primary transition-colors p-2 border border-outline-variant hover:border-primary rounded-sm bg-surface/50"
            >
              <Share2 className="h-4 w-4" />
            </a>
            <a
              href="#"
              aria-label="Email"
              className="text-on-surface-variant hover:text-primary transition-colors p-2 border border-outline-variant hover:border-primary rounded-sm bg-surface/50"
            >
              <Mail className="h-4 w-4" />
            </a>
            <a
              href="#"
              aria-label="Language"
              className="text-on-surface-variant hover:text-primary transition-colors p-2 border border-outline-variant hover:border-primary rounded-sm bg-surface/50"
            >
              <Globe className="h-4 w-4" />
            </a>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-8">
          <div>
            <h5 className="font-semibold text-xs tracking-[0.2em] text-on-surface uppercase mb-4">
              Navigation
            </h5>
            <div className="space-y-3">
              <a href="#" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Systems Architecture
              </a>
              <a href="#" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Component Catalog
              </a>
              <a href="#" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Global Logistics
              </a>
            </div>
          </div>
          <div>
            <h5 className="font-semibold text-xs tracking-[0.2em] text-on-surface uppercase mb-4">
              Legal
            </h5>
            <div className="space-y-3">
              <a href="#" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Terms of Service
              </a>
              <a href="#" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Security Whitepaper
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="w-full py-6 border-t border-outline-variant px-6 text-center bg-surface-container-low">
        <p className="text-xs text-on-surface-variant/60">
          © 2026 IE Industrial Technology. Engineered for Precision.
        </p>
      </div>
    </footer>
  );
}
