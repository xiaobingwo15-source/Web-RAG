import { ArrowRight } from 'lucide-react'

export function HeroSection() {
  return (
    <header className="relative min-h-[90vh] md:h-[80vh] flex items-center overflow-hidden pt-20">
      <div className="absolute inset-0 z-0">
        <img
          className="w-full h-full object-cover"
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuClCeOi1LespBMAgcwHIsIcTYBU7Xuz35IxRneVbpINOIWRU9d8PkrYyfZlhM-9xCu4edg9yq_MtOKJ1yQ8kbRgwyy2RTmHtY0XGJ632GXplb2OF3OffjU9k8WzmwgppxzxtyN5pUcZkaekGl99XotpPgaVTMetT1qJ72B-vrWoBMkpOc3ZQsgzKjOn20pRmDmXNFnx5ANb8DWhUwvZfLpQcJL-26UNZeS_dU6iPWfpWhPu0AndJkqZI55HVt5WV0v5emtm9ynBPGMr"
          alt="Precision manufacturing cleanroom and instrumentation"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-surface via-surface/90 to-transparent"></div>
      </div>
      
      <div className="relative z-10 px-6 md:px-12 max-w-[1440px] mx-auto w-full">
        <div className="max-w-2xl border-l-2 border-secondary pl-6 md:pl-8">
          <div className="flex flex-wrap items-center gap-2 mb-4 bg-surface-container-high/60 backdrop-blur-md px-3 py-1.5 border border-outline-variant rounded-sm w-fit">
            <span className="text-xs font-bold text-secondary">5.0</span>
            <div className="flex text-secondary gap-0.5">
              {"★".repeat(5)}
            </div>
            <span className="text-[10px] font-medium text-on-surface-variant uppercase tracking-wider">
              5 Google Reviews
            </span>
            <span className="text-outline-variant text-xs hidden sm:inline">|</span>
            <span className="text-[10px] font-medium text-on-surface-variant uppercase tracking-wider hidden sm:inline">
              Klang Electronics Repair Shop
            </span>
          </div>
          <span className="font-semibold text-xs tracking-[0.2em] text-on-surface-variant uppercase block mb-3">
            Premium Engineering &amp; Services
          </span>
          <h1 className="text-3xl md:text-5xl font-bold text-on-surface mb-6 uppercase tracking-tight leading-tight">
            Precision Engineered for <span className="text-secondary">Industrial Excellence</span>
          </h1>
          <p className="text-base md:text-lg text-on-surface-variant mb-8 max-w-lg leading-relaxed">
            Advanced circuit board solutions for heavy machinery and precision electronics. Designed for zero-failure environments.
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <a
              href="#solutions"
              className="bg-primary text-on-primary hover:bg-primary-container px-6 py-4 font-semibold text-xs rounded-sm tracking-widest uppercase flex items-center justify-center gap-2 transition-all duration-200 active:scale-95"
            >
              View Catalog
              <ArrowRight className="h-4 w-4" />
            </a>
            <a
              href="#capabilities"
              className="border border-outline text-on-surface hover:bg-surface-variant px-6 py-4 font-semibold text-xs rounded-sm tracking-widest uppercase transition-all duration-200 active:scale-95"
            >
              Technical Specs
            </a>
          </div>
        </div>
      </div>
    </header>
  );
}

