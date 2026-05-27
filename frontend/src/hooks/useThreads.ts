import { useState, useEffect, useCallback } from 'react'
import { useAuth } from './useAuth'
import { getThreads, deleteThread, type ThreadSummary } from '@/lib/api'

export function useThreads() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null)
  const { session } = useAuth()

  const refreshThreads = useCallback(async () => {
    if (!session?.access_token) return
    try {
      const data = await getThreads(session.access_token)
      setThreads(data)
    } catch (err) {
      console.error('Failed to fetch threads:', err)
    }
  }, [session?.access_token])

  useEffect(() => {
    refreshThreads()
  }, [refreshThreads])

  const removeThread = async (threadId: string) => {
    if (!session?.access_token) return
    await deleteThread(threadId, session.access_token)
    setThreads((prev) => prev.filter((t) => t.id !== threadId))
    if (selectedThreadId === threadId) {
      setSelectedThreadId(null)
    }
  }

  return {
    threads,
    selectedThreadId,
    setSelectedThreadId,
    refreshThreads,
    removeThread,
  }
}
