import { useState, useEffect, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { isAdmin } from '@/lib/roles'
import { 
  User, 
  Lock, 
  Mail, 
  ArrowRight, 
  ArrowLeft, 
  ShieldCheck, 
  Database, 
  LockKeyhole, 
  Menu
} from 'lucide-react'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { signIn, signUp } = useAuth()
  const navigate = useNavigate()

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

    const { error } = isSignUp ? await signUp(email, password) : await signIn(email, password)

    if (error) {
      setError(error.message)
    } else {
      // Redirect based on role
      if (isAdmin(email)) {
        navigate('/admin')
      } else {
        navigate('/chat')
      }
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-background text-on-surface flex flex-col font-sans selection:bg-primary selection:text-on-primary relative overflow-hidden">
      
      {/* Top Navbar */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-surface border-b border-outline-variant">
        <div className="flex justify-between items-center w-full px-6 md:px-12 h-16 max-w-[1440px] mx-auto">
          <Link to="/" className="text-lg md:text-xl font-bold text-primary hover:opacity-90 active:scale-95 transition-all">
            IE Industrial Portal
          </Link>
          
          <nav className="hidden md:flex gap-6 items-center">
            <Link to="/" className="text-xs font-semibold text-on-surface-variant hover:text-primary transition-all uppercase tracking-wider">
              Main Site
            </Link>
            <a href="#support" className="text-xs font-semibold text-on-surface-variant hover:text-primary transition-all uppercase tracking-wider">
              Technical Support
            </a>
          </nav>
          
          <div className="md:hidden">
            <Menu className="h-5 w-5 text-primary cursor-pointer" />
          </div>
        </div>
      </header>

      {/* Main Canvas with Custom Dot Grid */}
      <main className="flex-grow flex items-center justify-center pt-16 pb-12 relative min-h-[calc(100vh-160px)] z-10 px-4">
        
        {/* Background Overlay Asset */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <img 
            alt="Industrial tech interface" 
            className="w-full h-full object-cover opacity-35 mix-blend-luminosity" 
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuBrHAIVRDtYn55yX6zB2cGOMhD8j9xQlcwQmeJWuO1QMmEp8TQqKP0sqdWVkifmOWRmUGKbx_J4RF8TrGBslBaDPQvw6MwTcOsVeJIBtIFrJYaAbMpOly-5JHIHjECPHy1vJUgDICnityOXihi9-GFPJAGBO-CxfalvZKSEnH_bM4A19FR4VE71rIECCT7mZVMavmmr-Mkp4Ycm5z0D1BnE2KFXulqw0hpK1ANHFMj2_IWgxA5SGcLL7IiVNpcsZSEm14FCBVsISzka"
          />
          {/* Radial mouse-glow tracking backdrop */}
          <div 
            ref={overlayRef}
            className="absolute inset-0 transition-all duration-300 pointer-events-none"
            style={{
              background: 'linear-gradient(180deg, rgba(18, 20, 23, 0.4) 0%, rgba(18, 20, 23, 0.8) 100%)'
            }}
          />
        </div>

        {/* Dynamic Card Container */}
        <div className="relative z-10 w-full max-w-[440px] animate-in fade-in slide-in-from-bottom-4 duration-700">
          
          {/* Main Card */}
          <div className="bg-surface-container-low border border-outline-variant p-8 shadow-2xl relative backdrop-blur-sm">
            
            {/* Top Indicator Strip (Signup only) */}
            {isSignUp && <div className="absolute -top-px left-0 right-0 h-0.5 bg-primary"></div>}

            {/* Decorative Industrial Corner Accents */}
            <div className="absolute top-0 left-0 w-2 h-2 border-t-2 border-l-2 border-primary"></div>
            <div className="absolute top-0 right-0 w-2 h-2 border-t-2 border-r-2 border-primary"></div>
            <div className="absolute bottom-0 left-0 w-2 h-2 border-b-2 border-l-2 border-primary"></div>
            <div className="absolute bottom-0 right-0 w-2 h-2 border-b-2 border-r-2 border-primary"></div>

            {/* Card Header */}
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight text-on-surface mb-1">
                {isSignUp ? 'Initialize Access' : 'Systems Access'}
              </h1>
              <p className="text-sm text-on-surface-variant">
                {isSignUp 
                  ? 'Create your secure industrial node credentials.' 
                  : 'Secure terminal for Industrial Tech Corp personnel.'}
              </p>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-6">
              
              {/* Email / Operator ID Field */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-on-surface-variant uppercase tracking-wider block" htmlFor="email">
                  {isSignUp ? 'Network Email Identifier' : 'Operator ID / Email'}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    {isSignUp ? (
                      <Mail className="h-4.5 w-4.5 text-outline" />
                    ) : (
                      <User className="h-4.5 w-4.5 text-outline" />
                    )}
                  </div>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full bg-surface-container-lowest border border-outline-variant text-on-surface text-sm rounded-none py-3 pl-11 pr-4 outline-none focus:border-primary transition-all duration-200"
                    placeholder={isSignUp ? 'user@industrial.tech' : 'name@ind-tech.com'}
                  />
                </div>
              </div>

              {/* Password Field */}
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <label className="text-xs font-bold text-on-surface-variant uppercase tracking-wider block" htmlFor="password">
                    {isSignUp ? 'Security Passphrase' : 'Access Token / Password'}
                  </label>
                  {!isSignUp && (
                    <a href="#forgot" className="text-xs text-primary hover:underline transition-all">
                      Forgot?
                    </a>
                  )}
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-4.5 w-4.5 text-outline" />
                  </div>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={6}
                    className="w-full bg-surface-container-lowest border border-outline-variant text-on-surface text-sm rounded-none py-3 pl-11 pr-4 outline-none focus:border-primary transition-all duration-200"
                    placeholder={isSignUp ? '••••••••••••' : '••••••••'}
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
                    'AUTHORIZING NODE...'
                  ) : (
                    <>
                      <span>{isSignUp ? 'CREATE ACCOUNT' : 'Initialize Login'}</span>
                      <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                    </>
                  )}
                </button>

                {/* Switch link */}
                <div className="text-center">
                  {isSignUp ? (
                    <button
                      type="button"
                      onClick={() => {
                        setIsSignUp(false)
                        setError('')
                      }}
                      className="text-on-surface-variant font-medium hover:text-primary transition-colors text-xs flex items-center justify-center gap-1 group mx-auto cursor-pointer"
                    >
                      <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-0.5 transition-transform" />
                      <span>Back to Login</span>
                    </button>
                  ) : (
                    <p className="text-xs text-on-surface-variant">
                      Need access?{' '}
                      <button
                        type="button"
                        onClick={() => {
                          setIsSignUp(true)
                          setError('')
                        }}
                        className="text-secondary font-bold hover:underline transition-all cursor-pointer"
                      >
                        Create an account
                      </button>
                    </p>
                  )}
                </div>
              </div>
            </form>

            {/* Technical Footer of Card */}
            {isSignUp ? (
              <div className="mt-8 pt-4 border-t border-outline-variant/30 flex justify-between items-center">
                <div className="flex flex-col">
                  <span className="text-[10px] font-bold text-outline tracking-wider uppercase">SECURITY STATUS</span>
                  <span className="text-secondary flex items-center gap-1.5 font-medium text-xs">
                    <span className="w-1.5 h-1.5 bg-secondary rounded-full animate-pulse"></span>
                    AES-256 Encrypted
                  </span>
                </div>
                <div className="flex gap-2">
                  <div className="w-8 h-8 rounded border border-outline-variant flex items-center justify-center text-outline hover:text-primary hover:border-primary transition-all cursor-pointer">
                    <ShieldCheck className="h-4.5 w-4.5" />
                  </div>
                  <div className="w-8 h-8 rounded border border-outline-variant flex items-center justify-center text-outline hover:text-primary hover:border-primary transition-all cursor-pointer">
                    <Database className="h-4.5 w-4.5" />
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-8 pt-4 border-t border-outline-variant/30 flex justify-between items-center opacity-40 text-[10px] font-bold text-outline">
                <div className="flex items-center gap-1">
                  <LockKeyhole className="h-3 w-3" />
                  <span>SSL 256-BIT ENCRYPTION</span>
                </div>
                <div>v4.1.0-NODE_8</div>
              </div>
            )}
          </div>
        </div>

        {/* System Coordinates (Sign Up View Coordinate marker) */}
        {isSignUp && (
          <div className="hidden xl:block absolute bottom-12 left-12 z-10">
            <div className="flex flex-col gap-1 text-outline/40">
              <span className="text-[10px] font-bold tracking-wider">SYSTEM_COORD</span>
              <span className="font-mono text-[11px]">40.7128° N, 74.0060° W</span>
            </div>
          </div>
        )}
      </main>

      {/* Global Page Footer */}
      <footer className="w-full mt-auto bg-surface-container border-t border-outline-variant z-10">
        <div className="flex flex-col md:flex-row justify-between items-center w-full px-6 md:px-12 py-6 max-w-[1440px] mx-auto gap-4">
          <div className="flex flex-col md:items-start items-center">
            <span className="text-sm font-bold text-primary mb-0.5">IE Industrial Portal</span>
            <span className="text-xs text-on-surface-variant">© 2026 Industrial Tech Corp. All rights reserved.</span>
          </div>
          <div className="flex flex-wrap justify-center gap-6 text-xs text-on-surface-variant font-semibold uppercase tracking-wider">
            <a className="hover:text-secondary transition-colors" href="#privacy">Privacy Policy</a>
            <a className="hover:text-secondary transition-colors" href="#terms">Terms of Service</a>
            <a className="hover:text-secondary transition-colors" href="#security">Security Architecture</a>
            <a className="hover:text-secondary transition-colors" href="#support">Contact Support</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
