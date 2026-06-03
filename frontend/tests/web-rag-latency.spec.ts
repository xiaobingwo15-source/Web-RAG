import { expect, test, type Page } from '@playwright/test'

const PUBLIC_INTERACTIVE_MS = Number(process.env.PERF_PUBLIC_INTERACTIVE_MS || 2_000)
const CLICK_FEEDBACK_MS = Number(process.env.PERF_CLICK_FEEDBACK_MS || 100)
const ROUTE_FEEDBACK_MS = Number(process.env.PERF_ROUTE_FEEDBACK_MS || 300)
const ADMIN_TAB_MS = Number(process.env.PERF_ADMIN_TAB_MS || 300)

async function expectNoAppCrash(page: Page) {
  await expect(page.locator('body')).not.toContainText(/vite|webpack|runtime error|uncaught exception/i)
}

async function measure<T>(action: () => Promise<T>): Promise<{ result: T; duration: number }> {
  const startedAt = performance.now()
  const result = await action()
  return { result, duration: performance.now() - startedAt }
}

async function measureAppInteraction(page: Page, name: string, action: () => Promise<void>): Promise<number> {
  const eventPromise = page.evaluate((interactionName) => new Promise<number>((resolve) => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ name: string; duration_ms: number }>
      if (custom.detail?.name !== interactionName) return
      window.removeEventListener('web-rag:interaction', handler)
      resolve(custom.detail.duration_ms)
    }
    window.addEventListener('web-rag:interaction', handler)
  }), name)
  await action()
  return eventPromise
}

test('public route and widget interactions stay responsive', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))

  const route = await measure(async () => {
    await page.goto('/')
    await expect(page.getByText(/IE Industrial/i).first()).toBeVisible()
  })
  expect(route.duration).toBeLessThan(PUBLIC_INTERACTIVE_MS)
  await expectNoAppCrash(page)
  expect(errors).toEqual([])

  const openDuration = await measureAppInteraction(page, 'widget.open', async () => {
    await page.locator('button.fixed').click()
    await expect(page.getByText('IE Industrial Technology')).toBeVisible()
  })
  expect(openDuration).toBeLessThan(CLICK_FEEDBACK_MS)

  const sendDuration = await measureAppInteraction(page, 'widget.send', async () => {
    await page.getByPlaceholder(/Ask about/i).fill('What services are available?')
    await page.locator('textarea[placeholder*="Ask about"] + button').click()
    await expect(page.getByPlaceholder(/Ask about/i)).toHaveValue('')
  })
  expect(sendDuration).toBeLessThan(CLICK_FEEDBACK_MS)
})

test('public navigation and protected route redirects are responsive', async ({ page }) => {
  await page.goto('/')

  const loginNavDuration = await measureAppInteraction(page, 'nav.portal', async () => {
    await page.getByRole('link', { name: /portal|login|sign in/i }).first().click()
    await expect(page).toHaveURL(/\/login/)
  })
  expect(loginNavDuration).toBeLessThan(ROUTE_FEEDBACK_MS)
  const loginReady = await measure(async () => {
    await expect(page.locator('input[type="email"]')).toBeVisible()
  })
  expect(loginReady.duration).toBeLessThan(PUBLIC_INTERACTIVE_MS)

  await page.goto('/chat')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.locator('input[type="email"]')).toBeVisible()

  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.locator('input[type="email"]')).toBeVisible()
})

test('authenticated admin tabs and network-backed actions show fast feedback', async ({ page }) => {
  const email = process.env.E2E_ADMIN_EMAIL
  const password = process.env.E2E_ADMIN_PASSWORD
  test.skip(!email || !password, 'Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD to run authenticated admin latency checks.')

  await page.goto('/login')
  await page.locator('input[type="email"]').fill(email!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/(dashboard|admin|chat)/)
  await page.goto('/admin')
  await expect(page.getByText('Admin Workspace')).toBeVisible()

  for (const tab of ['Users', 'Settings', 'Evals', 'Chats']) {
    const tabSwitch = await measure(async () => {
      await page.getByRole('button', { name: new RegExp(tab, 'i') }).click()
      await expect(page.getByRole('button', { name: new RegExp(tab, 'i') })).toBeVisible()
    })
    expect(tabSwitch.duration).toBeLessThan(ADMIN_TAB_MS)
  }

  const refresh = await measure(async () => {
    await page.getByRole('button', { name: /refresh/i }).first().click()
    await expect(page.getByRole('button', { name: /refresh/i }).first()).toBeDisabled()
  })
  expect(refresh.duration).toBeLessThan(CLICK_FEEDBACK_MS)
})
