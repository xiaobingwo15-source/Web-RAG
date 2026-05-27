import { useState, useEffect } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'
import { getUserProfile } from '@/lib/api'

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadRole = async (sess: Session | null) => {
      if (sess?.access_token) {
        try {
          const profile = await getUserProfile(sess.access_token)
          setRole(profile.role)
        } catch (err) {
          console.error('Failed to load user role:', err)
          const isHardcodedAdmin = sess.user?.email?.toLowerCase() === 'admin@example.com'
          setRole(isHardcodedAdmin ? 'admin' : 'client')
        }
      } else {
        setRole(null)
      }
    }

    supabase.auth.getSession().then(async ({ data: { session } }) => {
      setSession(session)
      setUser(session?.user ?? null)
      await loadRole(session)
      setLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      setSession(session)
      setUser(session?.user ?? null)
      await loadRole(session)
      setLoading(false)
    })

    return () => subscription.unsubscribe()
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

  return { user, session, role, loading, signIn, signUp, signOut }
}

