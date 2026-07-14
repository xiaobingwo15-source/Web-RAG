import { expect, test, type Page, type Route } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const TOKEN = 'playwright-admin-token'

function readEnvValue(key: string): string | undefined {
  if (process.env[key]) return process.env[key]

  const envFiles = [
    path.join(process.cwd(), '.env.local'),
    path.join(process.cwd(), '.env'),
    path.join(process.cwd(), '..', '.env.local'),
    path.join(process.cwd(), '..', '.env'),
  ]

  for (const file of envFiles) {
    if (!fs.existsSync(file)) continue
    const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/)
    for (const line of lines) {
      const match = line.match(/^\s*([^#=\s]+)\s*=\s*(.*)\s*$/)
      if (!match || match[1] !== key) continue
      return match[2].trim().replace(/^['"]|['"]$/g, '')
    }
  }

  return undefined
}

function supabaseStorageKey(url: string): string {
  return `sb-${new URL(url).hostname.split('.')[0]}-auth-token`
}

async function seedSupabaseSession(page: Page, storageKey: string) {
  const now = Math.floor(Date.now() / 1000)
  await page.addInitScript(
    ({ key, session }) => {
      window.localStorage.setItem(key, JSON.stringify(session))
    },
    {
      key: storageKey,
      session: {
        access_token: TOKEN,
        refresh_token: 'playwright-refresh-token',
        token_type: 'bearer',
        expires_in: 3600,
        expires_at: now + 3600,
        user: {
          id: 'admin-user',
          aud: 'authenticated',
          role: 'authenticated',
          email: 'admin@example.com',
          app_metadata: { provider: 'email', providers: ['email'] },
          user_metadata: {},
          created_at: '2026-01-01T00:00:00.000Z',
          updated_at: '2026-01-01T00:00:00.000Z',
        },
      },
    },
  )
}

async function json(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test('admin Quality Inbox filters items, dismisses a flag, and renders audit activity', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  let dismissed = false

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))

  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'admin@example.com', role: 'admin', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/admin/conversations', (route) =>
    json(route, {
      clients: [{
        email: 'client@example.com',
        user_id: 'client-user',
        threads: [{ id: 'thread-1', title: 'Refund issue', created_at: '2026-01-01T00:00:00.000Z', message_count: 2 }],
      }],
    }),
  )
  await page.route('**/api/admin/conversations/thread-1/messages', (route) =>
    json(route, {
      messages: [
        {
          id: 'question-1',
          thread_id: 'thread-1',
          user_id: 'client-user',
          role: 'user',
          content: 'What is the refund rule?',
          created_at: '2026-01-01T00:01:00.000Z',
        },
        {
          id: 'answer-1',
          thread_id: 'thread-1',
          user_id: 'client-user',
          role: 'assistant',
          content: 'Refunds are available anytime.',
          created_at: '2026-01-01T00:02:00.000Z',
        },
      ],
    }),
  )
  await page.route('**/api/admin/flagged/count', (route) => json(route, { count: dismissed ? 0 : 1 }))
  await page.route('**/api/admin/flagged', (route) =>
    json(route, {
      flagged: dismissed
        ? []
        : [{
          message_id: 'message-flag',
          thread_id: 'thread-1',
          thread_title: 'Refund issue',
          client_email: 'client@example.com',
          client_user_id: 'client-user',
          content: 'I do not have that information in my knowledge base.',
          created_at: '2026-01-01T00:02:00.000Z',
          has_admin_response: false,
        }],
    }),
  )
  await page.route('**/api/admin/flagged/message-flag/dismiss', async (route) => {
    dismissed = true
    await json(route, { status: 'dismissed', message_id: 'message-flag' })
  })
  await page.route('**/api/admin/rag-evals/cases', (route) => json(route, []))
  await page.route('**/api/admin/rag-evals/runs', (route) => json(route, []))
  await page.route('**/api/admin/rag-quality/feedback?*', (route) =>
    json(route, {
      items: [
        {
          feedback_id: 'feedback-positive',
          feedback_created_at: '2026-01-01T00:04:00.000Z',
          feedback_comment: 'Helpful and correct',
          rating: 1,
          message_id: 'answer-2',
          resolved_message_id: 'answer-2',
          thread_id: 'thread-1',
          thread_title: 'Refund issue',
          client_user_id: 'client-user',
          client_email: 'client@example.com',
          question: 'What documents are required?',
          answer: 'Include the original invoice.',
          retrieval_logs: [],
          summary: {
            retrieval_count: 1,
            chunk_count: 1,
            source_count: 1,
            top_score: 0.91,
            groundedness_score: 0.96,
            groundedness_flag: false,
            zero_source: false,
          },
        },
        {
          feedback_id: 'feedback-1',
          feedback_created_at: '2026-01-01T00:03:00.000Z',
          feedback_comment: 'Wrong refund window',
          rating: -1,
          message_id: 'answer-1',
          resolved_message_id: 'answer-1',
          thread_id: 'thread-1',
          thread_title: 'Refund issue',
          client_user_id: 'client-user',
          client_email: 'client@example.com',
          question: 'What is the refund rule?',
          answer: 'Refunds are available anytime.',
          retrieval_logs: [],
          summary: {
            retrieval_count: 1,
            chunk_count: 0,
            source_count: 0,
            top_score: null,
            groundedness_score: 0.25,
            groundedness_flag: true,
            zero_source: true,
          },
        },
      ],
    }),
  )
  await page.route('**/api/admin/rag-quality/signals?*', (route) =>
    json(route, {
      window_hours: 168,
      limit: 50,
      totals: { retrieval_count: 1 },
      signals: [{
        id: 'zero_sources',
        label: 'Zero Sources',
        description: 'Queries with no retrieved source chunks.',
        status: 'critical',
        count: 1,
        rate: 1,
        threshold: 0.1,
        examples: [{
          id: 'log-1',
          query: 'missing policy',
          created_at: '2026-01-01T00:04:00.000Z',
          retrieval_mode: 'hybrid',
          reason: 'No sources',
          details: { thread_id: 'thread-1', channel: 'authenticated', source_count: 0 },
        }],
      }],
    }),
  )
  await page.route('**/api/admin/audit-logs?*', (route) =>
    json(route, {
      logs: [{
        id: 'audit-1',
        actor_email: 'admin@example.com',
        actor_role: 'admin',
        action: 'flagged_message.dismiss',
        resource_type: 'message',
        resource_id: 'message-flag',
        created_at: '2026-01-01T00:05:00.000Z',
      }],
    }),
  )

  await page.goto('/admin')
  await page.getByRole('button', { name: /evals/i }).click()

  await expect(page.getByRole('button', { name: /Quality Inbox/i })).toHaveClass(/bg-primary/)
  await expect(page.getByText('Wrong refund window')).toBeVisible()
  await expect(page.getByText('Helpful and correct')).not.toBeVisible()
  await expect(page.getByText('flagged_message.dismiss')).toBeVisible()

  await page.getByLabel('Quality inbox type').selectOption('flagged')
  await expect(page.getByText('I do not have that information in my knowledge base.')).toBeVisible()
  await expect(page.getByText('Wrong refund window')).not.toBeVisible()

  await page.getByRole('button', { name: 'Dismiss' }).click()
  await expect(page.getByText('Flag dismissed')).toBeVisible()

  await page.getByRole('button', { name: /Feedback Review/i }).click()
  await expect(page.getByText('Helpful and correct').first()).toBeVisible()
  await expect(page.getByText('Wrong refund window')).toBeVisible()

  await page.getByRole('button', { name: /Quality Inbox/i }).click()
  await page.getByLabel('Quality inbox type').selectOption('feedback')
  await page.getByRole('button', { name: 'Open', exact: true }).click()

  await expect(page.getByText('Client Conversations')).toBeVisible()
  await expect(page.getByText('Refunds are available anytime.', { exact: true })).toBeVisible()
  await expect(page.getByText('Feedback target', { exact: true })).toBeVisible()
  await expect(page.getByText('Wrong refund window', { exact: true })).toBeVisible()
})
