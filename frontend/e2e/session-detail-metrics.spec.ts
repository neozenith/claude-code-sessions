import { test, expect, Page } from '@playwright/test'

/**
 * Session Detail Tokenometrics E2E (G7 / T7.3)
 *
 * On a real session, the detail page renders per-event context-occupancy bars
 * (width ∝ raw context_ratio), TPS on assistant response heads, and an idle-gap
 * marker between turns. Follows the discovery pattern from
 * session-detail-filter.spec.ts (no fixed session id).
 *
 * NOTE: requires a backend serving SCHEMA_VERSION >= 17 data (the occupancy /
 * tps / idle fields). Run with `make test-frontend-e2e` after a reingest.
 */

test.setTimeout(60000)

const TEST_PROJECT_ID = '-Users-joshpeak-play-claude-code-sessions'

async function discoverSessionId(page: Page): Promise<string> {
  await page.goto(`/sessions/${encodeURIComponent(TEST_PROJECT_ID)}`)
  await page.waitForSelector('tbody tr a', { timeout: 30000 })
  const href = await page.locator('tbody tr a').first().getAttribute('href')
  const parts = href?.split('/') ?? []
  return parts[parts.length - 1] ?? ''
}

test('session detail shows occupancy, tps and idle markers', async ({ page }) => {
  const sessionId = await discoverSessionId(page)
  expect(sessionId, 'discovered a session id').not.toBe('')

  await page.goto(
    `/sessions/${encodeURIComponent(TEST_PROJECT_ID)}/${encodeURIComponent(sessionId)}`,
  )
  await page.waitForFunction(() => document.body.innerText.includes('Event Timeline'), {
    timeout: 45000,
  })

  // Per-event context-occupancy bar (raw context_ratio, no zone colors).
  await expect(page.locator('[data-testid="context-occupancy-bar"]').first()).toBeVisible({
    timeout: 15000,
  })
  // TPS on at least one assistant response head.
  await expect(page.locator('[data-testid="response-tps"]').first()).toBeVisible()
  // Idle-gap marker between turns (real sessions are multi-turn).
  await expect(page.locator('[data-testid="idle-gap"]').first()).toBeVisible()
})
