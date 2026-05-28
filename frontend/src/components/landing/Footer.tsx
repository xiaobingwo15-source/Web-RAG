import { Share2, Mail, Globe, MapPin, Phone, Clock, Award } from 'lucide-react'

export function Footer() {
  return (
    <footer className="bg-surface-container border-t border-outline-variant mt-24">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 w-full py-16 px-6 md:px-12 max-w-[1440px] mx-auto">
        {/* Left Brand Column */}
        <div className="lg:col-span-5">
          <div className="font-semibold text-xs tracking-[0.2em] text-on-surface uppercase mb-4">
            IE Industrial Electronics Technology
          </div>
          <p className="text-on-surface-variant text-sm leading-relaxed max-w-md mb-4">
            A premium electronics repair and precision systems engineering facility in Klang. Calibrated for zero-failure industrial vertical markets.
          </p>
          <div className="flex items-center gap-2 mb-6 bg-surface/50 border border-outline-variant rounded px-2.5 py-1.5 w-fit">
            <Award className="text-secondary h-4 w-4" />
            <span className="text-xs font-bold text-secondary">5.0</span>
            <div className="flex text-secondary gap-0.5 text-xs">
              {"★".repeat(5)}
            </div>
            <span className="text-[10px] font-semibold text-on-surface-variant uppercase tracking-wider">
              5 Google Reviews
            </span>
          </div>
          <div className="flex gap-4">
            <a
              href="#"
              aria-label="Share"
              className="text-on-surface-variant hover:text-primary transition-colors p-2 border border-outline-variant hover:border-primary rounded-sm bg-surface/50"
            >
              <Share2 className="h-4 w-4" />
            </a>
            <a
              href="mailto:info@ieindustrial.com"
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

        {/* Right Columns */}
        <div className="lg:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-8">
          <div>
            <h5 className="font-semibold text-xs tracking-[0.2em] text-on-surface uppercase mb-4">
              Navigation
            </h5>
            <div className="space-y-3">
              <a href="#solutions" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Specializations
              </a>
              <a href="#capabilities" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Capabilities
              </a>
              <a href="#compliance" className="block text-sm text-on-surface-variant hover:text-primary transition-colors">
                Compliance Standards
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

          <div id="contact">
            <h5 className="font-semibold text-xs tracking-[0.2em] text-on-surface uppercase mb-4">
              Contact &amp; Location
            </h5>
            <div className="space-y-4">
              <div className="flex gap-2">
                <MapPin className="h-5 w-5 text-secondary shrink-0 mt-0.5" />
                <span className="text-xs text-on-surface-variant leading-relaxed">
                  Duro Metal Industrial (M) Sdn. Bhd., NO.117, BATU, Jalan Kapar, 42100 Klang, Selangor
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Phone className="h-4 w-4 text-secondary shrink-0" />
                <a href="tel:0163628633" className="text-xs text-on-surface-variant hover:text-primary transition-colors font-mono">
                  016-362 8633
                </a>
              </div>
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-secondary shrink-0" />
                <span className="text-xs text-on-surface-variant">
                  Opens 9:30 AM (Thu - Tue)
                </span>
              </div>
              <div className="text-[10px] text-on-surface-variant/70 border-t border-outline-variant/50 pt-2 font-mono">
                Transit: 21 mins 🚆
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="w-full py-6 border-t border-outline-variant px-6 text-center bg-surface-container-low">
        <p className="text-xs text-on-surface-variant/60">
          © 2026 IE Industrial Electronics Technology. All rights reserved.
        </p>
      </div>
    </footer>
  );
}

