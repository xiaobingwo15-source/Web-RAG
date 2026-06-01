import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  KeyRound,
  Lock,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  UserCheck,
  X,
} from 'lucide-react'
import {
  approveOwnerAdmin,
  getOwnerAdmins,
  rejectOwnerAdmin,
  type OwnerAdminProfile,
  type OwnerAdminStatus,
} from '@/lib/api'

const OWNER_KEY_STORAGE = 'owner_api_key'
const PAGE_LIMIT = 50

const filters: Array<{ value: OwnerAdminStatus; label: string }> = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'suspended', label: 'Rejected' },
  { value: 'all', label: 'All' },
]

function statusClasses(status: string) {
  if (status === 'approved') return 'border-green-500/30 bg-green-500/10 text-green-400'
  if (status === 'pending') return 'border-amber-500/30 bg-amber-500/10 text-amber-400'
  return 'border-destructive/30 bg-destructive/10 text-destructive'
}

function formatDate(value: string) {
  if (!value) return 'Unknown'
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function OwnerLockPage() {
  const [ownerKey, setOwnerKey] = useState(() => sessionStorage.getItem(OWNER_KEY_STORAGE) || '')
  const [keyInput, setKeyInput] = useState(ownerKey)
  const [status, setStatus] = useState<OwnerAdminStatus>('pending')
  const [page, setPage] = useState(1)
  const [admins, setAdmins] = useState<OwnerAdminProfile[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mutating, setMutating] = useState<string | null>(null)

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_LIMIT)), [total])

  const lockPage = () => {
    sessionStorage.removeItem(OWNER_KEY_STORAGE)
    setOwnerKey('')
    setKeyInput('')
    setAdmins([])
    setTotal(0)
    setError(null)
  }

  const loadAdmins = useCallback(async () => {
    if (!ownerKey) return
    setLoading(true)
    setError(null)
    try {
      const data = await getOwnerAdmins(ownerKey, { status, page, limit: PAGE_LIMIT })
      setAdmins(data.admins)
      setTotal(data.total)
    } catch (err) {
      const message = (err as Error).message || 'Failed to load owner admin approvals'
      setError(message)
      if (message.toLowerCase().includes('owner access')) {
        sessionStorage.removeItem(OWNER_KEY_STORAGE)
        setOwnerKey('')
      }
    } finally {
      setLoading(false)
    }
  }, [ownerKey, page, status])

  useEffect(() => {
    loadAdmins()
  }, [loadAdmins])

  const unlock = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = keyInput.trim()
    if (!trimmed) {
      setError('Owner key is required.')
      return
    }
    sessionStorage.setItem(OWNER_KEY_STORAGE, trimmed)
    setOwnerKey(trimmed)
    setPage(1)
    setError(null)
  }

  const runAction = async (admin: OwnerAdminProfile, action: 'approve' | 'reject') => {
    if (!ownerKey) return
    setMutating(`${admin.id}:${action}`)
    setError(null)
    try {
      if (action === 'approve') {
        await approveOwnerAdmin(ownerKey, admin.id)
      } else {
        await rejectOwnerAdmin(ownerKey, admin.id)
      }
      await loadAdmins()
    } catch (err) {
      setError((err as Error).message || `Failed to ${action} admin`)
    } finally {
      setMutating(null)
    }
  }

  if (!ownerKey) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-4 text-foreground">
        <form onSubmit={unlock} className="w-full max-w-sm rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
              <Lock className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-semibold">Owner Approval Lock</h1>
              <p className="text-xs text-muted-foreground">Enter the owner key to review admin access.</p>
            </div>
          </div>
          {error && (
            <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <label className="mb-1.5 block text-xs font-semibold text-muted-foreground">OWNER_API_KEY</label>
          <div className="relative">
            <KeyRound className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <input
              type="password"
              value={keyInput}
              onChange={(event) => setKeyInput(event.target.value)}
              className="w-full rounded-md border border-border bg-input py-2 pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-ring"
              autoComplete="off"
            />
          </div>
          <button
            type="submit"
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-95"
          >
            <ShieldCheck className="h-4 w-4" />
            Unlock
          </button>
        </form>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card/70 px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10">
              <UserCheck className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-semibold">Owner Admin Approvals</h1>
              <p className="text-xs text-muted-foreground">{total} matching admin account{total === 1 ? '' : 's'}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadAdmins}
              disabled={loading}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              onClick={lockPage}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <ShieldOff className="h-3.5 w-3.5" />
              Lock
            </button>
          </div>
        </div>
      </header>

      <section className="px-6 py-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex rounded-md border border-border bg-card p-1">
            {filters.map((filter) => (
              <button
                key={filter.value}
                onClick={() => {
                  setStatus(filter.value)
                  setPage(1)
                }}
                className={`rounded px-3 py-1.5 text-xs font-semibold transition ${
                  status === filter.value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <button
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={page <= 1 || loading}
              className="rounded-md border border-border p-1.5 hover:bg-muted disabled:opacity-40"
              title="Previous page"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            Page {page} of {totalPages}
            <button
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              disabled={page >= totalPages || loading}
              className="rounded-md border border-border p-1.5 hover:bg-muted disabled:opacity-40"
              title="Next page"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="grid grid-cols-[1.2fr_1fr_1.3fr_110px_150px_150px] gap-4 border-b border-border bg-muted/30 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <span>Email</span>
            <span>Tenant</span>
            <span>User ID</span>
            <span>Status</span>
            <span>Created</span>
            <span>Actions</span>
          </div>
          {loading ? (
            <div className="flex h-48 items-center justify-center">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : admins.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
              No admin accounts match this filter.
            </div>
          ) : (
            admins.map((admin) => {
              const approveKey = `${admin.id}:approve`
              const rejectKey = `${admin.id}:reject`
              return (
                <div
                  key={admin.id}
                  className="grid grid-cols-[1.2fr_1fr_1.3fr_110px_150px_150px] items-center gap-4 border-b border-border/60 px-4 py-3 text-sm last:border-b-0 hover:bg-muted/20"
                >
                  <span className="truncate font-medium">{admin.email || 'Unknown email'}</span>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold">{admin.tenant?.name || 'Unknown tenant'}</p>
                    <p className="truncate text-[10px] text-muted-foreground">{admin.tenant?.slug || admin.tenant_id}</p>
                  </div>
                  <code className="truncate rounded bg-muted px-2 py-1 text-[11px] text-muted-foreground">{admin.id}</code>
                  <span className={`w-fit rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClasses(admin.status)}`}>
                    {admin.status}
                  </span>
                  <span className="text-xs text-muted-foreground">{formatDate(admin.created_at)}</span>
                  <div className="flex items-center gap-1.5">
                    {admin.status === 'pending' && (
                      <>
                        <button
                          onClick={() => runAction(admin, 'approve')}
                          disabled={Boolean(mutating)}
                          className="flex items-center gap-1 rounded-md bg-green-500/10 px-2.5 py-1 text-[11px] font-semibold text-green-400 hover:bg-green-500/20 disabled:opacity-50"
                        >
                          {mutating === approveKey ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                          Approve
                        </button>
                        <button
                          onClick={() => runAction(admin, 'reject')}
                          disabled={Boolean(mutating)}
                          className="flex items-center gap-1 rounded-md bg-destructive/10 px-2.5 py-1 text-[11px] font-semibold text-destructive hover:bg-destructive/20 disabled:opacity-50"
                        >
                          {mutating === rejectKey ? <RefreshCw className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
                          Reject
                        </button>
                      </>
                    )}
                    {admin.status === 'approved' && (
                      <button
                        onClick={() => runAction(admin, 'reject')}
                        disabled={Boolean(mutating)}
                        className="flex items-center gap-1 rounded-md bg-destructive/10 px-2.5 py-1 text-[11px] font-semibold text-destructive hover:bg-destructive/20 disabled:opacity-50"
                      >
                        {mutating === rejectKey ? <RefreshCw className="h-3 w-3 animate-spin" /> : <ShieldOff className="h-3 w-3" />}
                        Revoke
                      </button>
                    )}
                    {admin.status === 'suspended' && (
                      <span className="text-[11px] text-muted-foreground">No action</span>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </section>
    </main>
  )
}
