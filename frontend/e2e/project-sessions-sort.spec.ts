import { test, expect, Page } from '@playwright/test'

/**
 * Project Sessions Sort E2E Tests
 *
 * Tests sortable column headers on the /sessions/{project_id} page.
 * Verifies clicking column headers (Last Active, Events, Subagents, Cost)
 * changes sort order and updates the table accordingly.
 */

const TEST_PROJECT_ID = '-Users-joshpeak-play-claude-code-sessions'

test.setTimeout(60000)

async function waitForPageLoad(page: Page): Promise<void> {
  await page.waitForFunction(
    () => (document.getElementById('root')?.children.length ?? 0) > 0,
    { timeout: 45000 },
  )
  await page.waitForLoadState('networkidle', { timeout: 45000 }).catch(() => {})
  await page.waitForFunction(
    () => !document.body.innerText.includes('Loading...'),
    { timeout: 45000 },
  ).catch(() => {})
}

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

async function navigateToProjectSessions(page: Page): Promise<void> {
  await page.goto(`/sessions/${encodeURIComponent(TEST_PROJECT_ID)}`)
  await waitForPageLoad(page)
  // Wait for table body to appear (data loaded) or empty state
  await page.waitForSelector('tbody, [class*="py-12"]', { timeout: 10000 }).catch(() => {})
}

test.describe('Project Sessions - Sortable Columns', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToProjectSessions(page)
  })

  test('sortable column headers are visible', async ({ page }) => {
    await expect(page.getByTestId('sort-last_active')).toBeVisible()
    await expect(page.getByTestId('sort-events')).toBeVisible()
    await expect(page.getByTestId('sort-subagents')).toBeVisible()
    await expect(page.getByTestId('sort-cost')).toBeVisible()
  })

  test('default sort is Last Active descending with no sort param in URL', async ({ page }) => {
    // No ?sort= param for the default (last_active_desc keeps URL clean)
    expect(page.url()).not.toContain('sort=')
    const header = page.getByTestId('sort-last_active')
    await expect(header).toBeVisible()

    await page.screenshot({
      path: 'e2e-screenshots/project-sessions-default-sort.png',
      fullPage: true,
    })
  })

  test('clicking Last Active toggles asc/desc and updates URL', async ({ page }) => {
    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count < 2) test.skip()

    const header = page.getByTestId('sort-last_active')

    // Click once → toggles to asc, URL gets ?sort=last_active_asc
    await header.click()
    await waitForPageLoad(page)
    expect(page.url()).toContain('sort=last_active_asc')
    await page.screenshot({ path: 'e2e-screenshots/project-sessions-last-active-asc.png', fullPage: true })

    // Click again → back to default desc, ?sort param removed (clean URL)
    await header.click()
    await waitForPageLoad(page)
    expect(page.url()).not.toContain('sort=')
    await page.screenshot({ path: 'e2e-screenshots/project-sessions-last-active-desc.png', fullPage: true })
  })

  test('clicking Events sorts by event count and sets ?sort=events_desc', async ({ page }) => {
    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count < 2) test.skip()

    await page.getByTestId('sort-events').click()
    await waitForPageLoad(page)
    expect(page.url()).toContain('sort=events_desc')

    // Collect event counts from rows (4th column, 0-indexed = index 3)
    const cells = page.locator('tbody tr td:nth-child(4)')
    const values = await cells.allTextContents()
    const nums = values.map((v) => parseInt(v.replace(/,/g, ''), 10)).filter((n) => !isNaN(n))

    // Should be descending (first click on new column = desc)
    for (let i = 0; i < nums.length - 1; i++) {
      expect(nums[i]).toBeGreaterThanOrEqual(nums[i + 1])
    }

    await page.screenshot({
      path: 'e2e-screenshots/project-sessions-sort-events.png',
      fullPage: true,
    })
  })

  test('clicking Cost sorts by cost descending then ascending', async ({ page }) => {
    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count < 2) test.skip()

    // Click Cost header → desc
    await page.getByTestId('sort-cost').click()
    await waitForPageLoad(page)

    // 6th column (index 5) is Cost
    const costCells = page.locator('tbody tr td:nth-child(6)')
    const costTexts = await costCells.allTextContents()
    const parseCost = (s: string) => parseFloat(s.replace(/[$,]/g, '')) || 0
    const costValuesDesc = costTexts.map(parseCost)

    for (let i = 0; i < costValuesDesc.length - 1; i++) {
      expect(costValuesDesc[i]).toBeGreaterThanOrEqual(costValuesDesc[i + 1])
    }

    // Click again → asc
    await page.getByTestId('sort-cost').click()
    await waitForPageLoad(page)

    const costTextsAsc = await costCells.allTextContents()
    const costValuesAsc = costTextsAsc.map(parseCost)

    for (let i = 0; i < costValuesAsc.length - 1; i++) {
      expect(costValuesAsc[i]).toBeLessThanOrEqual(costValuesAsc[i + 1])
    }

    await page.screenshot({
      path: 'e2e-screenshots/project-sessions-sort-cost-asc.png',
      fullPage: true,
    })
  })

  test('clicking Subagents sorts by subagent count', async ({ page }) => {
    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count < 2) test.skip()

    await page.getByTestId('sort-subagents').click()
    await waitForPageLoad(page)

    // 5th column (index 4) is Subagents
    const cells = page.locator('tbody tr td:nth-child(5)')
    const texts = await cells.allTextContents()
    // "-" means 0
    const values = texts.map((t) => (t.trim() === '-' ? 0 : parseInt(t, 10) || 0))

    // Should be descending
    for (let i = 0; i < values.length - 1; i++) {
      expect(values[i]).toBeGreaterThanOrEqual(values[i + 1])
    }

    await page.screenshot({
      path: 'e2e-screenshots/project-sessions-sort-subagents.png',
      fullPage: true,
    })
  })

  test('switching sort column resets direction to desc', async ({ page }) => {
    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count < 2) test.skip()

    // First click Events (desc)
    await page.getByTestId('sort-events').click()
    await waitForPageLoad(page)

    // Then click Cost — should start desc (not inherit Events' state)
    await page.getByTestId('sort-cost').click()
    await waitForPageLoad(page)

    const costCells = page.locator('tbody tr td:nth-child(6)')
    const texts = await costCells.allTextContents()
    const costs = texts.map((s) => parseFloat(s.replace(/[$,]/g, '')) || 0)

    // First entry should be >= last (desc)
    if (costs.length >= 2) {
      expect(costs[0]).toBeGreaterThanOrEqual(costs[costs.length - 1])
    }
  })
})

test.describe('Project Sessions - Sort via Deep Link', () => {
  test('navigating directly to ?sort=cost_desc shows cost sort active', async ({ page }) => {
    await page.goto(`/sessions/${encodeURIComponent(TEST_PROJECT_ID)}?sort=cost_desc`)
    await waitForPageLoad(page)
    await page.waitForSelector('tbody, [class*="py-12"]', { timeout: 10000 }).catch(() => {})

    // Cost header should be the active sort
    const costHeader = page.getByTestId('sort-cost')
    await expect(costHeader).toBeVisible()
    // ChevronDown should be present (desc) — check the header is styled as active
    await expect(costHeader).toHaveClass(/text-foreground/)

    await page.screenshot({
      path: 'e2e-screenshots/project-sessions-deeplink-cost-desc.png',
      fullPage: true,
    })
  })

  test('navigating directly to ?sort=events_asc shows events asc sort active', async ({ page }) => {
    await page.goto(`/sessions/${encodeURIComponent(TEST_PROJECT_ID)}?sort=events_asc`)
    await waitForPageLoad(page)
    await page.waitForSelector('tbody, [class*="py-12"]', { timeout: 10000 }).catch(() => {})

    const rows = page.locator('tbody tr')
    const count = await rows.count()
    if (count < 2) test.skip()

    // Verify ascending sort — first row should have fewer events than last
    const cells = page.locator('tbody tr td:nth-child(4)')
    const texts = await cells.allTextContents()
    const nums = texts.map((v) => parseInt(v.replace(/,/g, ''), 10)).filter((n) => !isNaN(n))
    for (let i = 0; i < nums.length - 1; i++) {
      expect(nums[i]).toBeLessThanOrEqual(nums[i + 1])
    }
  })

  test('sort param is preserved when time filter changes', async ({ page }) => {
    await navigateToProjectSessions(page)

    // Sort by cost
    await page.getByTestId('sort-cost').click()
    await waitForPageLoad(page)
    expect(page.url()).toContain('sort=cost_desc')

    // Change time filter — sort param should survive
    const timeSelect = page.locator('select').first()
    await timeSelect.selectOption('7')
    await waitForPageLoad(page)

    expect(page.url()).toContain('sort=cost_desc')
    expect(page.url()).toContain('days=7')
  })
})
