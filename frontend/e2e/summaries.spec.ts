import { test, expect } from '@playwright/test'

/**
 * Summaries explorer E2E (G8) — shell smoke only.
 *
 * Per ADR8.2, data-dependent rendering (lens cards vs. not_summarised empty
 * state, variant prose) is unit-tested in `src/pages/Summaries.test.ts`; e2e
 * verifies the data-independent shell: the route mounts and the heading, grain
 * selector, and scope breadcrumb render against the real (summary-less) backend.
 */

test.setTimeout(60000)

test('summaries page mounts and renders the shell', async ({ page }) => {
  await page.goto('/summaries')
  await page.waitForFunction(() => document.body.innerText.includes('Summaries'), {
    timeout: 45000,
  })

  await expect(page.locator('[data-testid="grain-select"]')).toBeVisible({ timeout: 15000 })
  // Scope-lineage breadcrumb shell (the root "All" crumb renders at any scope).
  await expect(page.locator('[data-testid="scope-crumb-root"]')).toBeVisible()
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
