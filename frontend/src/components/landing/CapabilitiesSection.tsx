import { Shield, Wifi, Layers, Cpu } from 'lucide-react'

export function CapabilitiesSection() {
  return (
    <section id="capabilities" className="bg-surface-container-low py-24 border-y border-outline-variant scroll-mt-20">
      <div className="px-6 md:px-12 max-w-[1440px] mx-auto">
        <div className="mb-16 text-center">
          <span className="font-semibold text-xs tracking-[0.2em] text-secondary uppercase block mb-2">
            Engineering Parameters
          </span>
          <h2 className="text-3xl md:text-4xl font-bold text-on-surface">
            Technical Capabilities
          </h2>
        </div>
        
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Durability Card */}
          <div className="p-6 bg-surface-container border border-outline-variant rounded-sm relative crosshair-corner">
            <Shield className="text-secondary h-8 w-8 mb-4" />
            <h4 className="font-semibold text-xs tracking-wider uppercase text-on-surface mb-3">
              Durability
            </h4>
            <p className="text-on-surface-variant text-sm leading-relaxed">
              Engineered for operating temperatures ranging from -40°C to +125°C in extreme environments.
            </p>
          </div>

          {/* High-Frequency Card */}
          <div className="p-6 bg-surface-container border border-outline-variant rounded-sm relative crosshair-corner">
            <Wifi className="text-secondary h-8 w-8 mb-4" />
            <h4 className="font-semibold text-xs tracking-wider uppercase text-on-surface mb-3">
              High-Frequency
            </h4>
            <p className="text-on-surface-variant text-sm leading-relaxed">
              Optimized RF layouts supporting signal integrity for up to 10GHz industrial wireless protocols.
            </p>
          </div>

          {/* Multi-layer Card */}
          <div className="p-6 bg-surface-container border border-outline-variant rounded-sm relative crosshair-corner">
            <Layers className="text-secondary h-8 w-8 mb-4" />
            <h4 className="font-semibold text-xs tracking-wider uppercase text-on-surface mb-3">
              Multi-layer
            </h4>
            <p className="text-on-surface-variant text-sm leading-relaxed">
              Advanced fabrication supporting up to 32 layers with complex blind and buried via structures.
            </p>
          </div>

          {/* Custom Logic Card */}
          <div className="p-6 bg-surface-container border border-outline-variant rounded-sm relative crosshair-corner">
            <Cpu className="text-secondary h-8 w-8 mb-4" />
            <h4 className="font-semibold text-xs tracking-wider uppercase text-on-surface mb-3">
              Custom Logic
            </h4>
            <p className="text-on-surface-variant text-sm leading-relaxed">
              Integrated FPGA and custom SoC mounting with rigorous post-assembly stress testing.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
