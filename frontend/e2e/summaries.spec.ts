import { test, expect } from '@playwright/test'

/**
 * Summaries explorer E2E (G8 / T8.1)
 *
 * /summaries mounts the route, reads the default (root) scope via the G7 API,
 * and renders the three lens cards. The cards render whether or not the scope
 * is summarised (the not_summarised empty state is refined in T8.6); this
 * tracer only asserts the three lenses are present.
 */

test.setTimeout(60000)

test('summaries page renders the three lenses', async ({ page }) => {
  await page.goto('/summaries')
  await page.waitForFunction(() => document.body.innerText.includes('Summaries'), {
    timeout: 45000,
  })

  await expect(page.locator('[data-testid="lens-task"]')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('[data-testid="lens-patterns"]')).toBeVisible()
  await expect(page.locator('[data-testid="lens-decisions"]')).toBeVisible()
})

test('deep-link path and grain selects scope and grain', async ({ page }) => {
  await page.goto('/summaries?path=clients/acme&grain=week')
  await page.waitForFunction(() => document.body.innerText.includes('acme'), {
    timeout: 45000,
  })

  // The breadcrumb reflects ?path= (deepest crumb = the path leaf).
  const crumbs = page.locator('[data-testid="scope-crumb"]')
  await expect(crumbs.last()).toHaveText('acme')

  // The grain selector reflects ?grain=.
  await expect(page.locator('[data-testid="grain-select"]')).toHaveValue('week')
})
