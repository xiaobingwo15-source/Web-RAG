export type UserRole = 'admin' | 'client'

/**
 * Checks if the given value (either a role string or an email) represents an admin.
 */
export function isAdmin(roleOrEmail: string | undefined | null): boolean {
  if (!roleOrEmail) return false
  const val = roleOrEmail.toLowerCase()
  return val === 'admin'
}

export function getUserRole(roleOrEmail: string | undefined | null): UserRole {
  return isAdmin(roleOrEmail) ? 'admin' : 'client'
}
