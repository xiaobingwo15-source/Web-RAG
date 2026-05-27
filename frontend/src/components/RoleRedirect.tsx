import { Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { isAdmin } from '@/lib/roles'

/**
 * Redirects authenticated users to the correct page based on their role.
 * Admin emails → /admin, others → /chat.
 */
export function RoleRedirect() {
  const { user, role } = useAuth()
  
  if (isAdmin(role || user?.email)) {
    return <Navigate to="/admin" replace />
  }
  
  return <Navigate to="/chat" replace />
}
