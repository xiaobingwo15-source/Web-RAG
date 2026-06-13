import { useEffect } from 'react'
import { Navbar } from '@/components/landing/Navbar'
import { HeroSection } from '@/components/landing/HeroSection'
import { ServicesSection } from '@/components/landing/ServicesSection'
import { CapabilitiesSection } from '@/components/landing/CapabilitiesSection'
import { ComplianceSection } from '@/components/landing/ComplianceSection'
import { Footer } from '@/components/landing/Footer'
import { ChatWidget } from '@/components/landing/ChatWidget'
import { markRouteReady } from '@/lib/performance'

export function LandingPage() {
  useEffect(() => {
    markRouteReady('/')
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <HeroSection />
      <ServicesSection />
      <CapabilitiesSection />
      <ComplianceSection />
      <Footer />
      <ChatWidget />
    </div>
  )
}
