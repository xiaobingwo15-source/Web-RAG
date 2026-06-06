import { expect, test, type Page, type Route } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const THREAD_ID = 'thread-feedback-rehydration'
const TOKEN = 'playwright-access-token'

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
          id: 'user-feedback-rehydration',
          aud: 'authenticated',
          role: 'authenticated',
          email: 'client@example.com',
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

function formatBubbleTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function messageBubble(page: Page, text: string) {
  return page.getByText(text, { exact: true }).locator('xpath=ancestor::div[contains(@class,"rounded-lg")][1]')
}

async function expectBubbleTime(page: Page, text: string, iso: string) {
  await expect(messageBubble(page, text)).toContainText(formatBubbleTime(iso))
}

test('rehydrates saved assistant feedback after reopening a thread', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  let releaseFeedback: () => void = () => {}
  const feedbackGate = new Promise<void>((resolve) => {
    releaseFeedback = resolve
  })

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))

  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, {
      threads: [
        {
          id: THREAD_ID,
          title: 'Feedback Rehydration',
          created_at: '2026-01-01T00:00:00.000Z',
        },
      ],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/messages`, (route) =>
    json(route, {
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: 'Question one',
          created_at: '2026-01-01T00:00:00.000Z',
          reply_to: null,
        },
        {
          id: 'assistant-positive',
          role: 'assistant',
          content: 'Helpful answer',
          created_at: '2026-01-01T00:01:00.000Z',
          reply_to: null,
        },
        {
          id: 'user-2',
          role: 'user',
          content: 'Question two',
          created_at: '2026-01-01T00:02:00.000Z',
          reply_to: null,
        },
        {
          id: 'assistant-negative',
          role: 'assistant',
          content: 'Unhelpful answer',
          created_at: '2026-01-01T00:03:00.000Z',
          reply_to: null,
        },
      ],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/feedback`, async (route) => {
    await feedbackGate
    await json(route, {
      feedback: [
        { message_id: 'assistant-positive', rating: 1 },
        { message_id: 'assistant-negative', rating: -1 },
      ],
    })
  })

  await page.goto('/chat')
  await page.getByText('Feedback Rehydration').click()

  await expect(page.getByText('Helpful answer', { exact: true })).toBeVisible()
  await expect(page.getByText('Unhelpful answer', { exact: true })).toBeVisible()
  await expectBubbleTime(page, 'Question one', '2026-01-01T00:00:00.000Z')
  await expectBubbleTime(page, 'Helpful answer', '2026-01-01T00:01:00.000Z')
  await expectBubbleTime(page, 'Question two', '2026-01-01T00:02:00.000Z')
  await expectBubbleTime(page, 'Unhelpful answer', '2026-01-01T00:03:00.000Z')

  const goodButtons = page.getByLabel('Good response')
  const poorButtons = page.getByLabel('Poor response')

  await expect(goodButtons.first()).not.toHaveClass(/(^| )bg-\[#00A884\]\/10( |$)/)
  await expect(poorButtons.nth(1)).not.toHaveClass(/(^| )bg-\[#EF4444\]\/10( |$)/)

  releaseFeedback()

  await expect(goodButtons.first()).toHaveClass(/(^| )bg-\[#00A884\]\/10( |$)/)
  await expect(poorButtons.nth(1)).toHaveClass(/(^| )bg-\[#EF4444\]\/10( |$)/)
})

test('uses stream created_at metadata for new chat bubbles', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  const userCreatedAt = '2026-01-01T00:05:00.000Z'
  const assistantCreatedAt = '2026-01-01T00:06:00.000Z'

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))

  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) => json(route, { threads: [] }))
  await page.route('**/api/chat/stream', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        `data: ${JSON.stringify({
          type: 'user_message',
          thread_id: 'thread-live-timestamps',
          message_id: 'server-user-message',
          created_at: userCreatedAt,
        })}`,
        '',
        `data: ${JSON.stringify({
          type: 'token',
          thread_id: 'thread-live-timestamps',
          content: 'Streamed answer',
          done: false,
        })}`,
        '',
        `data: ${JSON.stringify({
          type: 'done',
          thread_id: 'thread-live-timestamps',
          message_id: 'server-assistant-message',
          created_at: assistantCreatedAt,
          done: true,
        })}`,
        '',
      ].join('\n'),
    })
  })

  await page.goto('/chat')
  await page.getByPlaceholder('Type a message').fill('Live question')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Live question', { exact: true })).toBeVisible()
  await expect(page.getByText('Streamed answer', { exact: true })).toBeVisible()
  await expectBubbleTime(page, 'Live question', userCreatedAt)
  await expectBubbleTime(page, 'Streamed answer', assistantCreatedAt)
})
