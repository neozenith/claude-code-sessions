import { test, expect } from '@playwright/test'

/**
 * Performance page E2E (G7 / T7.4)
 *
 * /performance renders the TPS-by-model chart, the context-ratio utilization
 * histogram, and the idle-vs-active split, honoring the global day/project
 * filters.
 *
 * NOTE: requires a backend serving SCHEMA_VERSION >= 17 data. Run with
 * `make test-frontend-e2e` after a reingest.
 */

test.setTimeout(60000)

test('performance page renders charts', async ({ page }) => {
  await page.goto('/performance')
  await page.waitForFunction(() => document.body.innerText.includes('Performance'), {
    timeout: 45000,
  })

  await expect(page.locator('[data-testid="perf-tps-chart"]')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('[data-testid="perf-context-histogram"]')).toBeVisible()
  await expect(page.locator('[data-testid="perf-idle-active"]')).toBeVisible()
})
