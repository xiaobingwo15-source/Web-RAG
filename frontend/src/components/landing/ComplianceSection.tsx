import { CheckCircle2 } from 'lucide-react'

export function ComplianceSection() {
  return (
    <section id="compliance" className="py-24 px-6 md:px-12 max-w-[1440px] mx-auto overflow-hidden scroll-mt-20">
      <div className="grid grid-cols-1 md:grid-cols-3 items-center gap-12">
        <div className="md:col-span-1">
          <h2 className="text-2xl md:text-3xl font-bold text-on-surface mb-6">
            Compliance &amp; Global Standards
          </h2>
          <p className="text-on-surface-variant text-sm md:text-base leading-relaxed mb-8">
            Every component leaving our facility undergoes a 42-point automated optical inspection (AOI) to ensure total compliance with international industrial safety and quality standards.
          </p>
          <div className="flex flex-wrap gap-4">
            <div className="flex items-center gap-2 bg-surface-container-high px-4 py-2 border border-outline-variant rounded-sm">
              <CheckCircle2 className="text-primary h-4 w-4" />
              <span className="font-semibold text-xs tracking-wider uppercase text-on-surface">
                ISO 9001:2015
              </span>
            </div>
            <div className="flex items-center gap-2 bg-surface-container-high px-4 py-2 border border-outline-variant rounded-sm">
              <CheckCircle2 className="text-primary h-4 w-4" />
              <span className="font-semibold text-xs tracking-wider uppercase text-on-surface">
                IPC-A-610 CLASS 3
              </span>
            </div>
          </div>
        </div>

        <div className="md:col-span-2 relative">
          <div className="relative w-full h-64 bg-surface-container border border-outline-variant flex items-center justify-center group overflow-hidden rounded-sm">
            {/* Tech aesthetic background grid */}
            <div 
              className="absolute inset-0 opacity-[0.03] pointer-events-none" 
              style={{
                backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)',
                backgroundSize: '20px 20px'
              }}
            ></div>
            
            <div className="z-10 flex gap-8 md:gap-12 flex-wrap justify-center items-center">
              <div className="text-center opacity-50 group-hover:opacity-100 transition-opacity duration-300">
                <div className="w-16 h-16 border border-outline-variant mb-2 flex items-center justify-center font-bold text-base md:text-lg text-on-surface rounded-sm bg-surface/50">
                  RoHS
                </div>
                <span className="text-[10px] tracking-wider uppercase font-semibold text-on-surface-variant">
                  Compliant
                </span>
              </div>
              <div className="text-center opacity-50 group-hover:opacity-100 transition-opacity duration-300">
                <div className="w-16 h-16 border border-outline-variant mb-2 flex items-center justify-center font-bold text-base md:text-lg text-on-surface rounded-sm bg-surface/50">
                  UL
                </div>
                <span className="text-[10px] tracking-wider uppercase font-semibold text-on-surface-variant">
                  Certified
                </span>
              </div>
              <div className="text-center opacity-50 group-hover:opacity-100 transition-opacity duration-300">
                <div className="w-16 h-16 border border-outline-variant mb-2 flex items-center justify-center font-bold text-base md:text-lg text-on-surface rounded-sm bg-surface/50">
                  CE
                </div>
                <span className="text-[10px] tracking-wider uppercase font-semibold text-on-surface-variant">
                  Standard
                </span>
              </div>
            </div>

            {/* Crosshair decorations */}
            <div className="absolute top-4 left-4 w-4 h-4 border-t border-l border-primary/40"></div>
            <div className="absolute top-4 right-4 w-4 h-4 border-t border-r border-primary/40"></div>
            <div className="absolute bottom-4 left-4 w-4 h-4 border-b border-l border-primary/40"></div>
            <div className="absolute bottom-4 right-4 w-4 h-4 border-b border-r border-primary/40"></div>
          </div>
        </div>
      </div>
    </section>
  );
}
