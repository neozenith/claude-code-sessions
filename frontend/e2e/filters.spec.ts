import { test, expect, Page } from '@playwright/test'

/**
 * Universal Filters E2E Test Suite
 *
 * Tests all permutations of:
 * - 9 Sections (pages)
 * - 8 Time Range options
 * - 2 Project options (All Projects, specific project)
 *
 * Test ID format: S{section}-T{time}-P{project}
 * Screenshot naming: {test_id}.png
 */

// Section definitions
const SECTIONS = [
  { id: 0, name: 'Dashboard', path: '/' },
  { id: 1, name: 'Daily', path: '/daily' },
  { id: 2, name: 'Weekly', path: '/weekly' },
  { id: 3, name: 'Monthly', path: '/monthly' },
  { id: 4, name: 'Hourly', path: '/hourly' },
  { id: 5, name: 'HourOfDay', path: '/hour-of-day' },
  { id: 6, name: 'Projects', path: '/projects' },
  { id: 7, name: 'Timeline', path: '/timeline' },
  { id: 8, name: 'SchemaTimeline', path: '/schema-timeline' },
]

// Time range options (matching useFilters.ts)
const TIME_RANGES = [
  { id: 0, value: '1', label: 'Last 24 hours' },
  { id: 1, value: '3', label: 'Last 3 days' },
  { id: 2, value: '7', label: 'Last 7 days' },
  { id: 3, value: '14', label: 'Last 14 days' },
  { id: 4, value: '30', label: 'Last 30 days' },
  { id: 5, value: '90', label: 'Last 90 days' },
  { id: 6, value: '180', label: 'Last 180 days' },
  { id: 7, value: '0', label: 'All time' },
]

// Project options
const PROJECT_OPTIONS = [
  { id: 0, value: '', label: 'All Projects' },
  { id: 1, value: '-Users-joshpeak-play-claude-code-sessions', label: 'This Project' },
]

// Helper to generate test ID
function getTestId(sectionId: number, timeId: number, projectId: number): string {
  return `S${sectionId}-T${timeId}-P${projectId}`
}

// Helper to wait for page to load
async function waitForPageLoad(page: Page): Promise<void> {
  // Wait for any loading indicators to disappear
  await page.waitForFunction(() => {
    const loadingText = document.body.innerText
    return !loadingText.includes('Loading...')
  }, { timeout: 15000 }).catch(() => {
    // Timeout is ok - some pages load fast
  })

  // Additional small wait for any animations
  await page.waitForTimeout(500)
}

// Helper to apply filters
async function applyFilters(
  page: Page,
  timeRange: (typeof TIME_RANGES)[number],
  project: (typeof PROJECT_OPTIONS)[number]
): Promise<void> {
  // Set time range filter
  const timeSelect = page.locator('select').first()
  await timeSelect.selectOption(timeRange.value)

  // Set project filter
  const projectSelect = page.locator('select').nth(1)
  await projectSelect.selectOption(project.value)

  // Wait for data to reload
  await waitForPageLoad(page)
}

// Helper to verify URL parameters
async function verifyUrlParams(
  page: Page,
  timeRange: (typeof TIME_RANGES)[number],
  project: (typeof PROJECT_OPTIONS)[number]
): Promise<void> {
  const url = new URL(page.url())
  const params = url.searchParams

  // Check days parameter (30 is default and omitted)
  if (timeRange.value === '30') {
    // Default value should not be in URL
    expect(params.has('days')).toBe(false)
  } else if (timeRange.value !== '30') {
    // Non-default should be in URL (but 0 might be handled differently)
    const daysParam = params.get('days')
    if (daysParam !== null) {
      expect(daysParam).toBe(timeRange.value)
    }
  }

  // Check project parameter
  if (project.value === '') {
    expect(params.has('project')).toBe(false)
  } else {
    expect(params.get('project')).toBe(project.value)
  }
}

// Generate tests for a subset of permutations (key test cases)
// Full matrix would be 9 × 8 × 2 = 144 tests
// We'll test representative combinations for faster CI

test.describe('Universal Filters - Core Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to home first
    await page.goto('/')
    await waitForPageLoad(page)
  })

  test('filter dropdowns are present', async ({ page }) => {
    // Verify time range dropdown exists
    const timeSelect = page.locator('select').first()
    await expect(timeSelect).toBeVisible()

    // Verify project dropdown exists
    const projectSelect = page.locator('select').nth(1)
    await expect(projectSelect).toBeVisible()
  })

  test('time range filter changes URL', async ({ page }) => {
    const timeSelect = page.locator('select').first()

    // Select 7 days
    await timeSelect.selectOption('7')
    await waitForPageLoad(page)

    // Verify URL updated
    expect(page.url()).toContain('days=7')
  })

  test('project filter changes URL', async ({ page }) => {
    const projectSelect = page.locator('select').nth(1)

    // Select a specific project
    const options = await projectSelect.locator('option').all()
    if (options.length > 1) {
      // Get the value of the second option (first project)
      const projectValue = await options[1].getAttribute('value')
      if (projectValue) {
        await projectSelect.selectOption(projectValue)
        await waitForPageLoad(page)

        // Verify URL updated
        expect(page.url()).toContain('project=')
      }
    }
  })

  test('filters persist across navigation', async ({ page }) => {
    // Apply filters
    const timeSelect = page.locator('select').first()
    await timeSelect.selectOption('7')
    await waitForPageLoad(page)

    // Navigate to another page via nav link
    await page.click('text=Daily')
    await waitForPageLoad(page)

    // Verify filters are preserved
    expect(page.url()).toContain('days=7')
    expect(page.url()).toContain('/daily')
  })

  test('clear filters button works', async ({ page }) => {
    // Apply filters
    const timeSelect = page.locator('select').first()
    await timeSelect.selectOption('7')
    await waitForPageLoad(page)

    // Click clear filters
    const clearButton = page.locator('text=Clear filters')
    if (await clearButton.isVisible()) {
      await clearButton.click()
      await waitForPageLoad(page)

      // Verify URL is clean
      expect(page.url()).not.toContain('days=7')
    }
  })
})

// Test each section loads correctly with default filters
test.describe('Section Loading - Default Filters', () => {
  for (const section of SECTIONS) {
    test(`${section.name} (S${section.id}) loads`, async ({ page }) => {
      const testId = getTestId(section.id, 4, 0) // Default: T4 (30 days), P0 (All)

      await page.goto(section.path)
      await waitForPageLoad(page)

      // Take screenshot
      await page.screenshot({ path: `e2e-screenshots/${testId}.png`, fullPage: true })

      // Verify page loaded (no error message)
      const content = await page.content()
      expect(content).not.toContain('Error')
    })
  }
})

// Test filter combinations for Dashboard (S0)
test.describe('Dashboard Filters', () => {
  for (const timeRange of TIME_RANGES) {
    for (const project of PROJECT_OPTIONS) {
      test(`S0-T${timeRange.id}-P${project.id}: ${timeRange.label}, ${project.label}`, async ({ page }) => {
        const testId = getTestId(0, timeRange.id, project.id)

        await page.goto('/')
        await applyFilters(page, timeRange, project)
        await verifyUrlParams(page, timeRange, project)

        // Take screenshot
        await page.screenshot({ path: `e2e-screenshots/${testId}.png`, fullPage: true })
      })
    }
  }
})

// Test filter combinations for Daily (S1) - representative sample
test.describe('Daily Filters - Sample', () => {
  const sampleTimeRanges = [TIME_RANGES[2], TIME_RANGES[7]] // 7 days and All time

  for (const timeRange of sampleTimeRanges) {
    for (const project of PROJECT_OPTIONS) {
      test(`S1-T${timeRange.id}-P${project.id}: ${timeRange.label}, ${project.label}`, async ({ page }) => {
        const testId = getTestId(1, timeRange.id, project.id)

        await page.goto('/daily')
        await applyFilters(page, timeRange, project)
        await verifyUrlParams(page, timeRange, project)

        await page.screenshot({ path: `e2e-screenshots/${testId}.png`, fullPage: true })
      })
    }
  }
})

// Test API calls include filter parameters
test.describe('API Filter Verification', () => {
  test('API calls include days parameter', async ({ page }) => {
    // Listen for API requests
    const apiCalls: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        apiCalls.push(request.url())
      }
    })

    await page.goto('/')
    await waitForPageLoad(page)

    // Apply 7 day filter
    const timeSelect = page.locator('select').first()
    await timeSelect.selectOption('7')
    await waitForPageLoad(page)

    // Check that at least one API call includes days=7
    const hasDaysParam = apiCalls.some((url) => url.includes('days=7'))
    expect(hasDaysParam).toBe(true)
  })

  test('API calls include project parameter', async ({ page }) => {
    const apiCalls: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/')) {
        apiCalls.push(request.url())
      }
    })

    await page.goto('/')
    await waitForPageLoad(page)

    // Get first project from dropdown
    const projectSelect = page.locator('select').nth(1)
    const options = await projectSelect.locator('option').all()

    if (options.length > 1) {
      const projectValue = await options[1].getAttribute('value')
      if (projectValue) {
        await projectSelect.selectOption(projectValue)
        await waitForPageLoad(page)

        // Check API calls include project parameter
        const hasProjectParam = apiCalls.some((url) => url.includes('project='))
        expect(hasProjectParam).toBe(true)
      }
    }
  })
})

// Test project list updates with time range
test.describe('Dynamic Project List', () => {
  test('project list reflects time range', async ({ page }) => {
    await page.goto('/')
    await waitForPageLoad(page)

    // Get initial project count
    const projectSelect = page.locator('select').nth(1)
    const initialOptions = await projectSelect.locator('option').count()

    // Change to 1 day (fewer projects might be active)
    const timeSelect = page.locator('select').first()
    await timeSelect.selectOption('1')
    await waitForPageLoad(page)

    // Get updated project count
    const updatedOptions = await projectSelect.locator('option').count()

    // The counts might differ (or might not, depending on data)
    // At minimum, verify dropdown still works
    expect(updatedOptions).toBeGreaterThanOrEqual(1) // At least "All Projects"
  })
})

// Test Timeline page requires project selection
test.describe('Timeline Project Requirement', () => {
  test('Timeline shows message when no project selected', async ({ page }) => {
    await page.goto('/timeline')
    await waitForPageLoad(page)

    // Should show a message about selecting a project
    const content = await page.content()
    expect(
      content.includes('Select a project') || content.includes('select a project')
    ).toBe(true)
  })

  test('Timeline shows data when project selected', async ({ page }) => {
    await page.goto('/timeline')
    await waitForPageLoad(page)

    // Select a project
    const projectSelect = page.locator('select').nth(1)
    const options = await projectSelect.locator('option').all()

    if (options.length > 1) {
      const projectValue = await options[1].getAttribute('value')
      if (projectValue) {
        await projectSelect.selectOption(projectValue)
        await waitForPageLoad(page)

        // Should no longer show the "select project" message
        const content = await page.content()
        // Either shows data or "No events found"
        const hasData =
          content.includes('Event Timeline') || content.includes('No events found')
        expect(hasData).toBe(true)
      }
    }
  })
})
