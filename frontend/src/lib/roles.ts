export type UserRole = 'admin' | 'client'

const ADMIN_EMAILS = [
  'admin@example.com',
]

/**
 * Checks if the given value (either a role string or an email) represents an admin.
 */
export function isAdmin(roleOrEmail: string | undefined | null): boolean {
  if (!roleOrEmail) return false
  const val = roleOrEmail.toLowerCase()
  if (val === 'admin') return true
  return ADMIN_EMAILS.includes(val)
}

export function getUserRole(roleOrEmail: string | undefined | null): UserRole {
  return isAdmin(roleOrEmail) ? 'admin' : 'client'
}

