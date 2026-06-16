import { useState, useEffect } from 'react'
import { useAuth } from './useAuth'
import { supabase } from '@/lib/supabase'
import { getFlaggedCount } from '@/lib/api'

export function useFlaggedNotifications() {
  const [flaggedCount, setFlaggedCount] = useState(0)
  const { session } = useAuth()

  // Fetch initial count on mount
  useEffect(() => {
    if (!session?.access_token) return
    getFlaggedCount(session.access_token)
      .then((data) => setFlaggedCount(data.count))
      .catch(console.error)
  }, [session?.access_token])

  // Subscribe to Realtime changes
  useEffect(() => {
    if (!session?.access_token) return

    const channel = supabase
      .channel('flagged-messages')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: 'attention_status=eq.needs_admin',
        },
        () => {
          setFlaggedCount((prev) => prev + 1)
        },
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'messages',
        },
        (payload) => {
          const old = payload.old as { attention_status?: string }
          if (old?.attention_status === 'needs_admin') {
            setFlaggedCount((prev) => Math.max(0, prev - 1))
          }
        },
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [session?.access_token])

  const dismissFlag = () => {
    setFlaggedCount((prev) => Math.max(0, prev - 1))
  }

  const refreshCount = async () => {
    if (!session?.access_token) return
    const data = await getFlaggedCount(session.access_token)
    setFlaggedCount(data.count)
  }

  return { flaggedCount, dismissFlag, refreshCount }
}
