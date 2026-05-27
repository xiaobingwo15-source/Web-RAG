export function ServicesSection() {
  return (
    <section id="solutions" className="scroll-mt-20 py-24 px-6 md:px-12 max-w-[1440px] mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-16 gap-6">
        <div>
          <span className="font-semibold text-xs tracking-[0.2em] text-secondary uppercase block mb-2">
            Our Specialization
          </span>
          <h2 className="text-3xl md:text-4xl font-bold text-on-surface">
            Specialized PCBA Solutions
          </h2>
        </div>
        <p className="text-on-surface-variant max-w-md text-sm md:text-base leading-relaxed">
          Our manufacturing process is calibrated for the most demanding technical requirements in industrial automation and heavy logistics.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
        {/* Large Machine Card */}
        <div className="group relative bg-surface-container border border-outline-variant overflow-hidden crosshair-corner rounded-sm flex flex-col justify-between">
          <div>
            <div className="aspect-video overflow-hidden">
              <img
                className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuClCeOi1LespBMAgcwHIsIcTYBU7Xuz35IxRneVbpINOIWRU9d8PkrYyfZlhM-9xCu4edg9yq_MtOKJ1yQ8kbRgwyy2RTmHtY0XGJ632GXplb2OF3OffjU9k8WzmwgppxzxtyN5pUcZkaekGl99XotpPgaVTMetT1qJ72B-vrWoBMkpOc3ZQsgzKjOn20pRmDmXNFnx5ANb8DWhUwvZfLpQcJL-26UNZeS_dU6iPWfpWhPu0AndJkqZI55HVt5WV0v5emtm9ynBPGMr"
                alt="Large Machine Circuit Boards"
              />
            </div>
            <div className="p-6 md:p-8">
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-xl md:text-2xl font-bold text-on-surface">
                  Large Machine Circuit Boards
                </h3>
                <span className="px-2 py-1 border border-secondary text-secondary font-semibold text-[10px] tracking-wider uppercase rounded-sm">
                  HEAVY DUTY
                </span>
              </div>
              <p className="text-on-surface-variant mb-6 text-sm md:text-base leading-relaxed">
                High-current capacity boards designed for prime movers, hydraulic controllers, and massive power distribution units.
              </p>
              <ul className="space-y-3 mb-8 border-t border-outline-variant pt-6">
                <li className="flex items-center gap-3 font-semibold text-xs tracking-wider uppercase text-on-surface">
                  <span className="w-2 h-2 bg-secondary rounded-sm"></span> 4oz Copper Weight Standard
                </li>
                <li className="flex items-center gap-3 font-semibold text-xs tracking-wider uppercase text-on-surface">
                  <span className="w-2 h-2 bg-secondary rounded-sm"></span> Vibration-Resistant Mounting
                </li>
                <li className="flex items-center gap-3 font-semibold text-xs tracking-wider uppercase text-on-surface">
                  <span className="w-2 h-2 bg-secondary rounded-sm"></span> Thermal Stress Mitigation
                </li>
              </ul>
            </div>
          </div>
          <div className="px-6 pb-6 md:px-8 md:pb-8">
            <button className="w-full py-4 border border-outline text-on-surface font-semibold text-xs tracking-widest uppercase hover:bg-secondary hover:border-secondary hover:text-on-secondary transition-all duration-200">
              Configure Component
            </button>
          </div>
          <div className="absolute top-4 right-4 text-white/5 font-mono text-[60px] font-bold pointer-events-none select-none">
            01
          </div>
        </div>

        {/* Small Machine Card */}
        <div className="group relative bg-surface-container border border-outline-variant overflow-hidden crosshair-corner rounded-sm flex flex-col justify-between">
          <div>
            <div className="aspect-video overflow-hidden">
              <img
                className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuComcU7ENuc7X_cGj6gtW3j3mYOhGKN1RjLDpIgSMcQuAIY1u5XKKf1tuKFIc5eUqdD3hmQMRvYnq1lbFI6MEuqioedz2nOcPMfXHM_y-xzJyjOdG0s2ydUnYvEd2pw_dNvuC3eTkUuL3n9Pe0Uy2ha6cy2q6pu31FDFguP8_tnAxSCmvsOeOJUxeDVzaHpTwr8gcmzSPpZr94Z1aKpun6OamYpP01w5yMqLepadt_2fgCWQF2g6IVVoMKMuNSRvMxmJcVTSWbK6x1-"
                alt="Small Machine Circuit Boards"
              />
            </div>
            <div className="p-6 md:p-8">
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-xl md:text-2xl font-bold text-on-surface">
                  Small Machine Circuit Boards
                </h3>
                <span className="px-2 py-1 border border-primary text-primary font-semibold text-[10px] tracking-wider uppercase rounded-sm">
                  PRECISION
                </span>
              </div>
              <p className="text-on-surface-variant mb-6 text-sm md:text-base leading-relaxed">
                Micro-circuitry optimized for precision robotics, sensor arrays, and high-speed data acquisition modules.
              </p>
              <ul className="space-y-3 mb-8 border-t border-outline-variant pt-6">
                <li className="flex items-center gap-3 font-semibold text-xs tracking-wider uppercase text-on-surface">
                  <span className="w-2 h-2 bg-primary rounded-sm"></span> 0.1mm Trace Precision
                </li>
                <li className="flex items-center gap-3 font-semibold text-xs tracking-wider uppercase text-on-surface">
                  <span className="w-2 h-2 bg-primary rounded-sm"></span> Low-Latency Signal Paths
                </li>
                <li className="flex items-center gap-3 font-semibold text-xs tracking-wider uppercase text-on-surface">
                  <span className="w-2 h-2 bg-primary rounded-sm"></span> HDI Multi-Layer Fabrication
                </li>
              </ul>
            </div>
          </div>
          <div className="px-6 pb-6 md:px-8 md:pb-8">
            <button className="w-full py-4 border border-outline text-on-surface font-semibold text-xs tracking-widest uppercase hover:bg-primary hover:border-primary hover:text-on-primary transition-all duration-200">
              Request Prototype
            </button>
          </div>
          <div className="absolute top-4 right-4 text-white/5 font-mono text-[60px] font-bold pointer-events-none select-none">
            02
          </div>
        </div>
      </div>
    </section>
  );
}

