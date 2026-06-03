import { test, expect } from '@playwright/test'

/**
 * Claims Explorer E2E (CR5) — shell smoke only.
 *
 * Per ADR8.2, data-dependent rendering (ranked claims, counts, the
 * not_summarised empty state, failures badge) is unit-tested in
 * `src/pages/ClaimsExplorer.test.ts`. E2E verifies the data-independent shell:
 * the route mounts, the model/grain/bucket selects render, and deep-linked
 * `?path=&grain=` URL state holds against the real backend.
 */

test.setTimeout(60000)

test('claims explorer mounts and renders the shell', async ({ page }) => {
  await page.goto('/claims')
  await page.waitForFunction(() => document.body.innerText.includes('Claims Explorer'), {
    timeout: 45000,
  })

  await expect(page.locator('[data-testid="claims-grain-select"]')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('[data-testid="claims-bucket-select"]')).toBeVisible()
  // Reindex-this-slice trigger (CR5) — shell-level: the button renders.
  await expect(page.locator('[data-testid="reindex-button"]')).toBeVisible()
  // Scope-lineage breadcrumb shell (the root "All" crumb renders at any scope).
  await expect(page.locator('[data-testid="scope-crumb-root"]')).toBeVisible()

  await page.screenshot({ path: 'e2e-screenshots/claims-explorer.png', fullPage: true })
})

test('deep-link path and grain holds URL state', async ({ page }) => {
  await page.goto('/claims?path=clients/acme&grain=month')
  await page.waitForFunction(() => document.body.innerText.includes('acme'), {
    timeout: 45000,
  })

  // The breadcrumb reflects ?path= (deepest crumb = the path leaf).
  const crumbs = page.locator('[data-testid="scope-crumb"]')
  await expect(crumbs.last()).toHaveText('acme')

  // The grain selector reflects ?grain=.
  await expect(page.locator('[data-testid="claims-grain-select"]')).toHaveValue('month')
})

test('window note describes the days-windowed aggregate (global filter)', async ({ page }) => {
  // Default landing: no bucket selected → the explorer shows the windowed aggregate.
  await page.goto('/claims')
  await page.waitForFunction(() => document.body.innerText.includes('Claims Explorer'), {
    timeout: 45000,
  })
  const note = page.locator('[data-testid="claims-window-note"]')
  await expect(note).toBeVisible({ timeout: 15000 })
  // Default window is 30 days; the note names the grain + the window.
  await expect(note).toContainText('all month claims')
  await expect(note).toContainText('the last 30 days')

  // Switching the global Time Range to All time re-labels the window.
  await page.goto('/claims?days=0')
  await expect(page.locator('[data-testid="claims-window-note"]')).toContainText('all time', {
    timeout: 15000,
  })
})
