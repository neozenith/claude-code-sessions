import { test, expect, Page } from '@playwright/test'

/**
 * Session Detail Message Kind Filter E2E Tests
 *
 * Tests the message kind filter dropdown on /sessions/{project_id}/{session_id}.
 * Verifies dropdown options, URL ?msg= param deep-linking, event count display,
 * and that page-local params don't leak into global navigation.
 */

test.setTimeout(60000)

const TEST_PROJECT_ID = '-Users-joshpeak-play-claude-code-sessions'
let TEST_SESSION_ID = ''

function collectConsoleErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (err) => errors.push(err.message))
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text())
  })
  return {
    errors,
    assertNoErrors() {
      const real = errors.filter(
        (e) => !e.includes('act(') && !e.includes('favicon') && !e.includes('[vite]'),
      )
      expect(real, `Browser console errors:\n${real.join('\n')}`).toHaveLength(0)
    },
  }
}

async function discoverSessionId(page: Page): Promise<string> {
  await page.goto(`/sessions/${encodeURIComponent(TEST_PROJECT_ID)}`)
  await page.waitForSelector('tbody tr a', { timeout: 30000 })
  const href = await page.locator('tbody tr a').first().getAttribute('href')
  const parts = href?.split('/') ?? []
  return parts[parts.length - 1] ?? ''
}

async function navigateToSession(page: Page, sessionId: string, extraParams = ''): Promise<void> {
  const url = `/sessions/${encodeURIComponent(TEST_PROJECT_ID)}/${encodeURIComponent(sessionId)}${extraParams}`
  await page.goto(url)
  await page.waitForFunction(
    () => document.body.innerText.includes('Event Timeline'),
    { timeout: 45000 },
  )
  await page.waitForTimeout(300)
}

test.describe('Session Detail - Message Kind Filter', () => {
  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    TEST_SESSION_ID = await discoverSessionId(page)
    await ctx.close()
  })

  test('filter dropdown is visible with "All messages" default', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID)

    const dropdown = page.getByTestId('msg-kind-filter')
    await expect(dropdown).toBeVisible()
    await expect(dropdown).toHaveValue('')

    // No ?msg= param in default state
    expect(page.url()).not.toContain('msg=')

    await page.screenshot({
      path: 'e2e-screenshots/session-detail-filter-default.png',
      fullPage: false,
    })
  })

  test('dropdown has all 10 options (All + 9 kinds)', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID)

    const dropdown = page.getByTestId('msg-kind-filter')
    const options = dropdown.locator('option')
    await expect(options).toHaveCount(10)

    // Verify the first option is "All messages"
    await expect(options.first()).toHaveText('All messages')
  })

  test('selecting "human" updates URL to ?msg=human and filters events', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID)

    // Get total count from header before filtering
    const header = page.locator('h3').filter({ hasText: 'Event Timeline' })
    const beforeText = await header.textContent()
    const totalMatch = beforeText?.match(/\((\d+) events\)/)
    const totalEvents = totalMatch ? parseInt(totalMatch[1]) : null

    // Select human filter
    const dropdown = page.getByTestId('msg-kind-filter')
    await dropdown.selectOption('human')
    await page.waitForTimeout(300)

    // URL should contain ?msg=human
    expect(page.url()).toContain('msg=human')

    // Header should show "X of Y events filtered"
    const afterText = await header.textContent()
    expect(afterText).toContain('events filtered')
    if (totalEvents !== null) {
      expect(afterText).toContain(`of ${totalEvents} events filtered`)
    }

    await page.screenshot({
      path: 'e2e-screenshots/session-detail-filter-human.png',
      fullPage: false,
    })
  })

  test('selecting "tool_use" filters and updates URL', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID)

    const dropdown = page.getByTestId('msg-kind-filter')
    await dropdown.selectOption('tool_use')
    await page.waitForTimeout(300)

    expect(page.url()).toContain('msg=tool_use')

    const header = page.locator('h3').filter({ hasText: 'Event Timeline' })
    const text = await header.textContent()
    expect(text).toContain('events filtered')
  })

  test('resetting to "All messages" removes ?msg= from URL', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID, '?msg=tool_use')

    const dropdown = page.getByTestId('msg-kind-filter')
    await expect(dropdown).toHaveValue('tool_use')

    // Reset to all
    await dropdown.selectOption('')
    await page.waitForTimeout(300)

    expect(page.url()).not.toContain('msg=')

    // Header should be back to total count format "(N events)"
    const header = page.locator('h3').filter({ hasText: 'Event Timeline' })
    const text = await header.textContent()
    expect(text).not.toContain('filtered')
  })

  test('deep-linking with ?msg=human shows filtered state on load', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID, '?msg=human')

    const dropdown = page.getByTestId('msg-kind-filter')
    await expect(dropdown).toHaveValue('human')

    const header = page.locator('h3').filter({ hasText: 'Event Timeline' })
    const text = await header.textContent()
    expect(text).toContain('events filtered')

    await page.screenshot({
      path: 'e2e-screenshots/session-detail-filter-deeplink-human.png',
      fullPage: false,
    })
  })

  test('deep-linking with ?msg=assistant_text shows filtered state', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID, '?msg=assistant_text')

    const dropdown = page.getByTestId('msg-kind-filter')
    await expect(dropdown).toHaveValue('assistant_text')

    const header = page.locator('h3').filter({ hasText: 'Event Timeline' })
    const text = await header.textContent()
    expect(text).toContain('events filtered')
  })

  test('?msg= param does not leak into sidebar navigation links', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID, '?msg=human')

    // Sidebar "Dashboard" link should NOT have ?msg=human
    const dashboardLink = page.locator('nav a').filter({ hasText: 'Dashboard' })
    const href = await dashboardLink.getAttribute('href')
    expect(href).not.toContain('msg=')
  })

  test('?msg= param is preserved alongside ?days= filter', async ({ page }) => {
    await navigateToSession(page, TEST_SESSION_ID)

    const dropdown = page.getByTestId('msg-kind-filter')
    await dropdown.selectOption('tool_use')
    await page.waitForTimeout(300)

    // URL has ?msg=tool_use
    expect(page.url()).toContain('msg=tool_use')

    // Navigate directly with both params to verify deep-link
    await page.goto(
      `/sessions/${encodeURIComponent(TEST_PROJECT_ID)}/${encodeURIComponent(TEST_SESSION_ID)}?msg=tool_use&days=7`
    )
    await page.waitForFunction(
      () => document.body.innerText.includes('Event Timeline'),
      { timeout: 20000 }
    )

    const dropdown2 = page.getByTestId('msg-kind-filter')
    await expect(dropdown2).toHaveValue('tool_use')
  })
})
