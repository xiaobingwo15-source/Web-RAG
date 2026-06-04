import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Mail, ArrowLeft, ArrowRight, CheckCircle, MessageSquare } from 'lucide-react'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const { resetPassword } = useAuth()

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
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
      {/* Top Navbar */}
      <header className="w-full">
        <div className="flex justify-between items-center w-full px-6 md:px-12 h-16 max-w-[1440px] mx-auto">
          <Link to="/" className="flex items-center gap-2 text-lg font-semibold text-primary hover:opacity-90 transition-opacity">
            <MessageSquare className="h-5 w-5" />
            <span>Web RAG</span>
          </Link>
          <Link to="/login" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors group">
            <ArrowLeft className="h-3.5 w-3.5 group-hover:-translate-x-0.5 transition-transform" />
            <span>Back to sign in</span>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-grow flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-surface rounded-2xl shadow-lg border border-border p-8">
            {sent ? (
              <>
                <div className="text-center mb-6">
                  <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary/10 mb-4">
                    <CheckCircle className="h-7 w-7 text-primary" />
                  </div>
                  <h1 className="text-2xl font-bold text-foreground mb-1">Check your email</h1>
                  <p className="text-sm text-muted-foreground">
                    We sent a password reset link to <span className="font-medium text-foreground">{email}</span>. Follow the link to set a new password.
                  </p>
                </div>
                <Link
                  to="/login"
                  className="group w-full bg-primary text-primary-foreground font-semibold text-sm py-2.5 rounded-lg flex justify-center items-center gap-2 hover:opacity-90 transition-all active:scale-[0.98]"
                >
                  <ArrowLeft className="h-4 w-4 group-hover:-translate-x-0.5 transition-transform" />
                  <span>Back to sign in</span>
                </Link>
              </>
            ) : (
              <>
                <div className="text-center mb-8">
                  <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary/10 mb-4">
                    <MessageSquare className="h-7 w-7 text-primary" />
                  </div>
                  <h1 className="text-2xl font-bold text-foreground mb-1">Reset password</h1>
                  <p className="text-sm text-muted-foreground">
                    Enter your email and we'll send you a link to reset your password.
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-5">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium text-foreground block" htmlFor="email">Email</label>
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

                  {error && (
                    <div className="p-3 bg-destructive/10 border border-destructive/30 text-destructive text-sm rounded-lg">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="group w-full bg-primary text-primary-foreground font-semibold text-sm py-2.5 rounded-lg flex justify-center items-center gap-2 hover:opacity-90 transition-all active:scale-[0.98] cursor-pointer disabled:opacity-50"
                  >
                    {loading ? (
                      'Sending...'
                    ) : (
                      <>
                        <span>Send reset link</span>
                        <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
                      </>
                    )}
                  </button>

                  <div className="text-center">
                    <Link to="/login" className="text-sm text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1">
                      <ArrowLeft className="h-3.5 w-3.5" />
                      <span>Back to sign in</span>
                    </Link>
                  </div>
                </form>
              </>
            )}
          </div>

          <p className="text-center text-xs text-muted-foreground mt-8">
            &copy; 2026 Web RAG. All rights reserved.
          </p>
        </div>
      </main>
    </div>
  )
}
