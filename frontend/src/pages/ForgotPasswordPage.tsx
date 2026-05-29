import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Mail, ArrowLeft, ArrowRight, CheckCircle } from 'lucide-react'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const { resetPassword } = useAuth()

  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (overlayRef.current && window.innerWidth > 1024) {
        const x = (e.clientX / window.innerWidth) * 100
        const y = (e.clientY / window.innerHeight) * 100
        overlayRef.current.style.background = `radial-gradient(circle at ${x}% ${y}%, rgba(159, 202, 255, 0.05) 0%, rgba(18, 20, 23, 0.8) 70%)`
      }
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    const { error } = await resetPassword(email)

    if (error) {
      setError(error.message)
    } else {
      setSent(true)
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-background text-on-surface flex flex-col font-sans selection:bg-primary selection:text-on-primary relative overflow-hidden">

      {/* Top Navbar */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-surface border-b border-outline-variant">
        <div className="flex justify-between items-center w-full px-6 md:px-12 h-16 max-w-[1440px] mx-auto">
          <Link to="/" className="text-lg md:text-xl font-bold text-primary hover:opacity-90 active:scale-95 transition-all">
            IE Industrial Electronics
          </Link>

          <Link to="/login" className="flex items-center gap-1.5 text-xs font-semibold text-on-surface-variant hover:text-primary transition-all uppercase tracking-wider group">
            <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-0.5 transition-transform" />
            <span>Back to Sign In</span>
          </Link>
        </div>
      </header>

      {/* Main Canvas */}
      <main className="flex-grow flex items-center justify-center pt-16 pb-12 relative min-h-[calc(100vh-160px)] z-10 px-4">

        {/* Background Overlay */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <div
            ref={overlayRef}
            className="absolute inset-0 transition-all duration-300 pointer-events-none"
            style={{
              background: 'linear-gradient(180deg, rgba(18, 20, 23, 0.4) 0%, rgba(18, 20, 23, 0.8) 100%)'
            }}
          />
        </div>

        {/* Card Container */}
        <div className="relative z-10 w-full max-w-[440px] animate-in fade-in slide-in-from-bottom-4 duration-700">

          <div className="bg-surface-container-low border border-outline-variant p-8 shadow-2xl relative backdrop-blur-sm">

            {/* Decorative Corner Accents */}
            <div className="absolute top-0 left-0 w-2 h-2 border-t-2 border-l-2 border-primary"></div>
            <div className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-primary"></div>
            <div className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-primary"></div>
            <div className="absolute bottom-0 right-0 w-2 h-2 border-b-2 border-r-2 border-primary"></div>

            {sent ? (
              <>
                <div className="mb-6">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="h-5 w-5 text-primary" />
                    <h1 className="text-2xl font-bold tracking-tight text-on-surface">
                      Check Your Email
                    </h1>
                  </div>
                  <p className="text-sm text-on-surface-variant">
                    We've sent a password reset link to <span className="text-on-surface font-medium">{email}</span>. Follow the link to set a new password.
                  </p>
                </div>

                <div className="pt-2 space-y-4">
                  <Link
                    to="/login"
                    className="group w-full bg-primary-container text-on-primary-container font-bold text-xs py-3.5 flex justify-center items-center gap-2 hover:bg-opacity-90 transition-all active:scale-[0.98] uppercase tracking-widest"
                  >
                    <ArrowLeft className="h-4 w-4 group-hover:-translate-x-1 transition-transform" />
                    <span>Back to Sign In</span>
                  </Link>
                </div>
              </>
            ) : (
              <>
                <div className="mb-6">
                  <h1 className="text-2xl font-bold tracking-tight text-on-surface mb-1">
                    Reset Password
                  </h1>
                  <p className="text-sm text-on-surface-variant">
                    Enter your email and we'll send you a link to reset your password.
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">

                  {/* Email Field */}
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-on-surface-variant uppercase tracking-wider block" htmlFor="email">
                      Email Address
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Mail className="h-4.5 w-4.5 text-outline" />
                      </div>
                      <input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="w-full bg-surface-container-lowest border border-outline-variant text-on-surface text-sm rounded-none py-3 pl-11 pr-4 outline-none focus:border-primary transition-all duration-200"
                        placeholder="name@example.com"
                      />
                    </div>
                  </div>

                  {/* Error Message */}
                  {error && (
                    <div className="p-3 bg-error-container/20 border border-error/30 text-error text-xs">
                      {error}
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div className="pt-2 space-y-4">
                    <button
                      type="submit"
                      disabled={loading}
                      className="group w-full bg-primary-container text-on-primary-container font-bold text-xs py-3.5 flex justify-center items-center gap-2 hover:bg-opacity-90 transition-all active:scale-[0.98] uppercase tracking-widest cursor-pointer disabled:opacity-50"
                    >
                      {loading ? (
                        'Sending...'
                      ) : (
                        <>
                          <span>Send Reset Link</span>
                          <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                        </>
                      )}
                    </button>

                    <div className="text-center">
                      <Link
                        to="/login"
                        className="text-on-surface-variant font-medium hover:text-primary transition-colors text-xs flex items-center justify-center gap-1 group mx-auto"
                      >
                        <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-0.5 transition-transform" />
                        <span>Back to Sign In</span>
                      </Link>
                    </div>
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full mt-auto bg-surface-container border-t border-outline-variant z-10">
        <div className="flex justify-center items-center w-full px-6 py-6 max-w-[1440px] mx-auto">
          <span className="text-xs text-on-surface-variant">
            &copy; 2026 IE Industrial Electronics. All rights reserved.
          </span>
        </div>
      </footer>
    </div>
  )
}
