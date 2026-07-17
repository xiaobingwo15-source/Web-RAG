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

test('recovers a refreshed streaming response when the persisted message completes', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  const startedAt = new Date().toISOString()
  let messageFetches = 0

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))
  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, {
      threads: [{ id: THREAD_ID, title: 'Refresh Recovery', created_at: startedAt }],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/feedback`, (route) => json(route, { feedback: [] }))
  await page.route(`**/api/chat/threads/${THREAD_ID}/messages`, (route) => {
    messageFetches += 1
    return json(route, {
      messages: [
        {
          id: 'user-refresh',
          role: 'user',
          content: 'Why is the information of the PTPTN?',
          created_at: startedAt,
          reply_to: null,
          status: 'complete',
        },
        {
          id: 'assistant-refresh',
          role: 'assistant',
          content: messageFetches === 1 ? '' : 'Recovered answer',
          created_at: startedAt,
          reply_to: null,
          status: messageFetches === 1 ? 'streaming' : 'complete',
        },
      ],
    })
  })

  await page.goto('/chat')
  await page.getByText('Refresh Recovery', { exact: true }).click()

  await expect(page.getByLabel('Assistant is typing')).toBeVisible()
  await expect(page.getByText('Recovered answer', { exact: true })).toBeVisible({ timeout: 10_000 })
  await expect(page.getByLabel('Assistant is typing')).not.toBeVisible()
  await expect(page.getByText('typing...', { exact: true })).not.toBeVisible()
  await expect(page.getByPlaceholder('Type a message')).toBeEnabled()
  expect(messageFetches).toBeGreaterThanOrEqual(2)
})

test('restores a failed question to the composer without resubmitting it', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  let streamRequests = 0
  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))
  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, {
      threads: [{ id: THREAD_ID, title: 'Retry Recovery', created_at: '2026-07-17T00:00:00Z' }],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/feedback`, (route) => json(route, { feedback: [] }))
  await page.route(`**/api/chat/threads/${THREAD_ID}/messages`, (route) =>
    json(route, {
      messages: [
        {
          id: 'assistant-context',
          role: 'assistant',
          content: 'Earlier answer',
          created_at: '2026-07-17T00:00:00Z',
          reply_to: null,
          status: 'complete',
        },
        {
          id: 'user-retry',
          role: 'user',
          content: JSON.stringify({
            text: 'Retry this question',
            images: ['data:image/png;base64,YQ=='],
          }),
          created_at: '2026-07-17T00:00:01Z',
          reply_to: 'assistant-context',
          status: 'complete',
        },
        {
          id: 'assistant-failed',
          role: 'assistant',
          content: '',
          created_at: '2026-07-17T00:00:02Z',
          reply_to: null,
          status: 'failed',
        },
      ],
    }),
  )
  await page.route('**/api/chat/stream', (route) => {
    streamRequests += 1
    return route.abort()
  })

  await page.goto('/chat')
  await page.getByText('Retry Recovery', { exact: true }).click()
  await expect(page.getByText('This response was interrupted. Please try again.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Retry question' }).click()

  await expect(page.getByPlaceholder('Type a message')).toHaveValue('Retry this question')
  await expect(page.getByAltText('Pasted 1')).toBeVisible()
  await expect(page.getByText('Replying to Assistant', { exact: true }).last()).toBeVisible()
  expect(streamRequests).toBe(0)
})

test('turns an already stale streaming placeholder into a retryable failure', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))
  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, {
      threads: [{ id: THREAD_ID, title: 'Stale Recovery', created_at: '2020-01-01T00:00:00Z' }],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/feedback`, (route) => json(route, { feedback: [] }))
  await page.route(`**/api/chat/threads/${THREAD_ID}/messages`, (route) =>
    json(route, {
      messages: [
        {
          id: 'user-stale',
          role: 'user',
          content: 'Question that was interrupted',
          created_at: '2020-01-01T00:00:00Z',
          reply_to: null,
          status: 'complete',
        },
        {
          id: 'assistant-stale',
          role: 'assistant',
          content: '',
          created_at: '2020-01-01T00:00:01Z',
          reply_to: null,
          status: 'streaming',
        },
      ],
    }),
  )

  await page.goto('/chat')
  await page.getByText('Stale Recovery', { exact: true }).click()

  await expect(page.getByText('This response was interrupted. Please try again.', { exact: true })).toBeVisible({ timeout: 1000 })
  await expect(page.getByRole('button', { name: 'Retry question' })).toBeVisible()
  await expect(page.getByText('typing...', { exact: true })).not.toBeVisible()
  await expect(page.getByPlaceholder('Type a message')).toBeEnabled()
})

test('continues refresh recovery after a transient polling error', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  const startedAt = new Date().toISOString()
  let messageFetches = 0
  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))
  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, { threads: [{ id: THREAD_ID, title: 'Transient Recovery', created_at: startedAt }] }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/feedback`, (route) => json(route, { feedback: [] }))
  await page.route(`**/api/chat/threads/${THREAD_ID}/messages`, (route) => {
    messageFetches += 1
    if (messageFetches === 2) {
      return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'temporary' }) })
    }
    return json(route, {
      messages: [
        { id: 'user-transient', role: 'user', content: 'Question', created_at: startedAt, reply_to: null, status: 'complete' },
        {
          id: 'assistant-transient',
          role: 'assistant',
          content: messageFetches >= 3 ? 'Recovered after retry' : '',
          created_at: startedAt,
          reply_to: null,
          status: messageFetches >= 3 ? 'complete' : 'streaming',
        },
      ],
    })
  })

  await page.goto('/chat')
  await page.getByText('Transient Recovery', { exact: true }).click()

  await expect(page.getByText('Recovered after retry', { exact: true })).toBeVisible({ timeout: 12_000 })
  await expect(page.getByPlaceholder('Type a message')).toBeEnabled()
  expect(messageFetches).toBeGreaterThanOrEqual(3)
})

test('ignores a slow thread response after the user switches threads', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  const threadA = 'thread-slow-a'
  const threadB = 'thread-fast-b'
  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))
  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, {
      threads: [
        { id: threadA, title: 'Slow Thread', created_at: '2026-07-17T00:00:00Z' },
        { id: threadB, title: 'Fast Thread', created_at: '2026-07-17T00:00:01Z' },
      ],
    }),
  )
  await page.route('**/api/chat/threads/*/feedback', (route) => json(route, { feedback: [] }))
  await page.route(`**/api/chat/threads/${threadA}/messages`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    await json(route, {
      messages: [{ id: 'assistant-a', role: 'assistant', content: 'Slow answer', created_at: '2026-07-17T00:00:00Z', reply_to: null, status: 'complete' }],
    })
  })
  await page.route(`**/api/chat/threads/${threadB}/messages`, (route) =>
    json(route, {
      messages: [{ id: 'assistant-b', role: 'assistant', content: 'Fast answer', created_at: '2026-07-17T00:00:01Z', reply_to: null, status: 'complete' }],
    }),
  )

  await page.goto('/chat')
  await page.getByText('Slow Thread', { exact: true }).click()
  await page.getByText('Fast Thread', { exact: true }).click()

  await expect(page.getByText('Fast answer', { exact: true })).toBeVisible()
  await page.waitForTimeout(1800)
  await expect(page.getByText('Slow answer', { exact: true })).not.toBeVisible()
})

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

test('keeps failed negative feedback unsaved and allows retry', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  let attempts = 0

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))
  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) => json(route, { documents: [] }))
  await page.route('**/api/chat/threads', (route) =>
    json(route, {
      threads: [{ id: THREAD_ID, title: 'Feedback Retry', created_at: '2026-01-01T00:00:00.000Z' }],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/messages`, (route) =>
    json(route, {
      messages: [
        { id: 'question-1', role: 'user', content: 'Question', created_at: '2026-01-01T00:00:00.000Z', reply_to: null },
        { id: 'answer-1', role: 'assistant', content: 'Answer to review', created_at: '2026-01-01T00:01:00.000Z', reply_to: null },
      ],
    }),
  )
  await page.route(`**/api/chat/threads/${THREAD_ID}/feedback`, (route) => json(route, { feedback: [] }))
  await page.route('**/api/chat/feedback', async (route) => {
    attempts += 1
    if (attempts === 1) {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Feedback could not be saved. Please try again.' }),
      })
      return
    }
    await json(route, { status: 'ok', id: 'feedback-1' })
  })

  await page.goto('/chat')
  await page.getByText('Feedback Retry', { exact: true }).click()
  await page.getByLabel('Poor response').click()
  await page.getByRole('button', { name: 'Submit', exact: true }).click()

  await expect(page.getByText('Feedback could not be saved. Please try again.')).toBeVisible()
  await expect(page.getByLabel('Poor response')).not.toHaveClass(/(^| )bg-\[#EF4444\]\/10( |$)/)

  await page.getByRole('button', { name: 'Submit', exact: true }).click()
  await expect(page.getByText('Feedback could not be saved. Please try again.')).not.toBeVisible()
  await expect(page.getByLabel('Poor response')).toHaveClass(/(^| )bg-\[#EF4444\]\/10( |$)/)
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

test('shows source details, prefills follow-up, and submits feedback comments', async ({ page }) => {
  const supabaseUrl = readEnvValue('VITE_SUPABASE_URL') ?? readEnvValue('SUPABASE_URL')
  test.skip(!supabaseUrl, 'Set VITE_SUPABASE_URL or SUPABASE_URL so Supabase auth storage can be seeded.')

  let feedbackPayload: Record<string, unknown> | null = null

  await seedSupabaseSession(page, supabaseStorageKey(supabaseUrl!))

  await page.route('**/api/auth/me', (route) =>
    json(route, { email: 'client@example.com', role: 'client', status: 'approved', tenant_id: 'tenant-1' }),
  )
  await page.route('**/api/documents', (route) =>
    json(route, {
      documents: [{
        id: 'doc-policy',
        filename: 'policy.pdf',
        status: 'processed',
        metadata: { title: 'Policy Handbook' },
      }],
    }),
  )
  await page.route('**/api/chat/threads', (route) => json(route, { threads: [] }))
  await page.route('**/api/chat/feedback', async (route) => {
    feedbackPayload = await route.request().postDataJSON()
    await json(route, { status: 'ok', id: 'feedback-1' })
  })
  await page.route('**/api/chat/stream', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        `data: ${JSON.stringify({
          type: 'user_message',
          thread_id: 'thread-source',
          message_id: 'server-user-message',
          created_at: '2026-01-01T00:05:00.000Z',
        })}`,
        '',
        `data: ${JSON.stringify({
          type: 'sources',
          thread_id: 'thread-source',
          sources: [{
            document_id: 'doc-policy',
            filename: 'policy.pdf',
            chunk_id: 'chunk-policy-1',
            score: 0.87,
            snippet: 'Refund claims must include an invoice and be submitted within 30 days.',
            retrieval_mode: 'hybrid',
            score_family: 'cohere_rerank',
            heading: 'Refunds',
            structural_type: 'section',
            page_start: 2,
            page_end: 2,
            breadcrumb_path: ['Policy Handbook', 'Refunds'],
          }],
        })}`,
        '',
        `data: ${JSON.stringify({
          type: 'token',
          thread_id: 'thread-source',
          content: 'Source-backed answer',
          done: false,
        })}`,
        '',
        `data: ${JSON.stringify({
          type: 'done',
          thread_id: 'thread-source',
          message_id: 'server-assistant-message',
          created_at: '2026-01-01T00:06:00.000Z',
          done: true,
        })}`,
        '',
      ].join('\n'),
    })
  })

  await page.goto('/chat')
  await page.getByPlaceholder('Ask about your documents...').fill('What is the refund rule?')
  await page.keyboard.press('Enter')

  await expect(page.getByText('Source-backed answer', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /policy\.pdf/i }).click()
  await expect(page.getByText('Policy Handbook / Refunds')).toBeVisible()
  await expect(page.getByText('Page 2')).toBeVisible()
  await expect(page.getByText(/cohere_rerank/)).toBeVisible()

  await page.getByRole('button', { name: 'Ask follow-up' }).click()
  await expect(page.getByPlaceholder('Ask about your documents...')).toHaveValue(/Ask a follow-up using policy\.pdf/)

  await page.getByLabel('Poor response').click()
  await page.getByRole('button', { name: 'Missing source' }).click()
  await page.getByPlaceholder('Add details for the admin').fill('Need exact page.')
  await page.getByRole('button', { name: 'Submit', exact: true }).click()

  await expect.poll(() => feedbackPayload).toMatchObject({
    thread_id: 'thread-source',
    message_id: 'server-assistant-message',
    rating: -1,
    comment: 'Missing source; Need exact page.',
  })
})
