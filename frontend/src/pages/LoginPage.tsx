import { useState, useEffect } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { validateTenantSlug, resolveTenant } from '@/lib/api'
import type { TenantInfo } from '@/lib/api'
import { markRouteReady } from '@/lib/performance'
import {
  Lock,
  Mail,
  ArrowRight,
  ArrowLeft,
  Eye,
  EyeOff,
  MessageSquare
} from 'lucide-react'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isSignUp, setIsSignUp] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [tenantInfo, setTenantInfo] = useState<TenantInfo | null>(null)
  const [tenantValidating, setTenantValidating] = useState(true)
  const { signIn, signUp } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    markRouteReady('/login')
  }, [])

  // Resolve tenant: try ?tenant= slug first, then auto-detect from domain
  useEffect(() => {
    const slug = searchParams.get('tenant')
    if (slug) {
      validateTenantSlug(slug)
        .then((info) => {
          setTenantInfo(info)
          setTenantValidating(false)
        })
        .catch(() => {
          setError('Invalid or inactive tenant. Please check your link.')
          setTenantValidating(false)
        })
    } else {
      resolveTenant()
        .then((info) => {
          setTenantInfo(info)
          setTenantValidating(false)
        })
        .catch(() => {
          setError('This domain is not configured for portal access.')
          setTenantValidating(false)
        })
    }
  }, [searchParams])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    if (isSignUp) {
      if (!tenantInfo) {
        setError('Cannot sign up without a valid tenant link.')
        setLoading(false)
        return
      }
      const { error } = await signUp(email, password, tenantInfo.slug)
      if (error) {
        setError(error.message)
      } else {
        navigate('/dashboard')
      }
    } else {
      const { error } = await signIn(email, password)
      if (error) {
        setError(error.message)
      } else {
        navigate('/dashboard')
      }
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="w-full">
        <div className="flex justify-between items-center w-full px-6 md:px-12 h-16 max-w-[1440px] mx-auto">
          <Link to="/" className="flex items-center gap-2 text-lg font-semibold text-primary hover:opacity-90 transition-opacity">
            <MessageSquare className="h-5 w-5" />
            <span>Web RAG</span>
          </Link>

          <Link to="/" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors group">
            <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-0.5 transition-transform" />
            <span>Back to home</span>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-grow flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          {/* Card */}
          <div className="bg-surface rounded-2xl shadow-lg border border-border p-8">
            {/* Header */}
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary/10 mb-4">
                <MessageSquare className="h-7 w-7 text-primary" />
              </div>
              <h1 className="text-2xl font-bold text-foreground mb-1">
                {isSignUp ? 'Create your account' : 'Welcome back'}
              </h1>
              <p className="text-sm text-muted-foreground">
                {isSignUp
                  ? 'Sign up to get started with your workspace.'
                  : 'Sign in to continue to your workspace.'}
              </p>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5" aria-disabled={tenantValidating}>
              {/* Email Field */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground block" htmlFor="email">
                  Email
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full bg-surface border border-border text-foreground text-sm rounded-lg py-2.5 pl-10 pr-4 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                    placeholder="you@example.com"
                  />
                </div>
              </div>

              {/* Password Field */}
              <div className="space-y-1.5">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-medium text-foreground block" htmlFor="password">
                    Password
                  </label>
                  {!isSignUp && (
                    <Link to="/forgot-password" className="text-xs text-primary hover:underline transition-all">
                      Forgot password?
                    </Link>
                  )}
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                    <Lock className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={6}
                    className="w-full bg-surface border border-border text-foreground text-sm rounded-lg py-2.5 pl-10 pr-10 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center cursor-pointer focus:outline-none"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4 text-muted-foreground hover:text-foreground transition-colors" />
                    ) : (
                      <Eye className="h-4 w-4 text-muted-foreground hover:text-foreground transition-colors" />
                    )}
                  </button>
                </div>
              </div>

              {/* Error Message */}
              {error && (
                <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-sm rounded-lg">
                  {error}
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading || tenantValidating}
                className="group w-full bg-primary text-primary-foreground font-semibold text-sm py-2.5 rounded-lg flex justify-center items-center gap-2 hover:opacity-90 transition-all active:scale-[0.98] cursor-pointer disabled:opacity-50"
              >
                {loading ? (
                  'Signing in...'
                ) : tenantValidating ? (
                  'Validating...'
                ) : (
                  <>
                    <span>{isSignUp ? 'Create account' : 'Sign in'}</span>
                    <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>

              {/* Switch link */}
              <div className="text-center pt-1">
                {isSignUp ? (
                  <button
                    type="button"
                    onClick={() => {
                      setIsSignUp(false)
                      setError('')
                    }}
                    className="text-sm text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1 cursor-pointer"
                  >
                    <ArrowLeft className="h-3.5 w-3.5" />
                    <span>Back to sign in</span>
                  </button>
                ) : tenantInfo ? (
                  <p className="text-sm text-muted-foreground">
                    Need access?{' '}
                    <button
                      type="button"
                      onClick={() => {
                        setIsSignUp(true)
                        setError('')
                      }}
                      className="text-primary font-medium hover:underline transition-all cursor-pointer"
                    >
                      Create an account
                    </button>
                  </p>
                ) : null}
              </div>
            </form>
          </div>

          {/* Footer */}
          <p className="text-center text-xs text-muted-foreground mt-8">
            &copy; 2026 Web RAG. All rights reserved.
          </p>
        </div>
      </main>
    </div>
  )
}
