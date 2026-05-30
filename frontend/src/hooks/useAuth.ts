import { createContext, createElement, useContext, useEffect, useRef, useState } from 'react'
import type { AuthError, Session, User } from '@supabase/supabase-js'
import type { ReactNode } from 'react'
import { supabase } from '@/lib/supabase'
import { getUserProfile } from '@/lib/api'

interface AuthContextValue {
  user: User | null
  session: Session | null
  role: string | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: AuthError | null }>
  signUp: (email: string, password: string) => Promise<{ error: AuthError | null }>
  signOut: () => Promise<{ error: AuthError | null }>
  resetPassword: (email: string) => Promise<{ error: AuthError | null }>
  updatePassword: (newPassword: string) => Promise<{ error: AuthError | null }>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const initialLoadDone = useRef(false)

  useEffect(() => {
    let mounted = true

    const loadSession = async (sess: Session | null, isInitial = false) => {
      // Only show loading spinner on the very first load, not on token refreshes
      if (isInitial || !initialLoadDone.current) {
        setLoading(true)
      }
      setSession(sess)
      setUser(sess?.user ?? null)

      if (sess?.access_token) {
        try {
          const profile = await getUserProfile(sess.access_token)
          if (mounted) setRole(profile.role)
        } catch (err) {
          console.error('Failed to load user role:', err)
          if (mounted) setRole('client')
        }
      } else {
        setRole(null)
      }

      if (mounted) {
        initialLoadDone.current = true
        setLoading(false)
      }
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      loadSession(session, true)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      await loadSession(session, false)
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [])

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error }
  }

  const signUp = async (email: string, password: string) => {
    const { error } = await supabase.auth.signUp({ email, password })
    return { error }
  }

  const signOut = async () => {
    const { error } = await supabase.auth.signOut()
    return { error }
  }

  const resetPassword = async (email: string) => {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: window.location.origin + '/reset-password',
    })
    return { error }
  }

  const updatePassword = async (newPassword: string) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword })
    return { error }
  }

  const value: AuthContextValue = {
    user,
    session,
    role,
    loading,
    signIn,
    signUp,
    signOut,
    resetPassword,
    updatePassword,
  }

  return createElement(AuthContext.Provider, { value }, children)
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
