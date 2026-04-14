import { test, expect, Page } from '@playwright/test'

/**
 * Universal Filters E2E Test Suite
 *
 * All permutation tests follow the same pattern:
 *   1. Navigate to page
 *   2. Apply filters (time range + project)
 *   3. Wait for full render
 *   4. Assert zero browser console errors
 *   5. Take a named screenshot
 *
 * Screenshot slug format:
 *   E{id}{engine}-S{id}{route}-T{id}{days}-P{id}.png
 *
 * To expand coverage, edit COVERAGE_MATRIX below.
 */

// ---------------------------------------------------------------------------
// Axes — each axis has an id (for lexicographic sort) and a human slug
// ---------------------------------------------------------------------------

const ENGINES = {
  duckdb: { id: 0, name: 'duckdb' },
  sqlite: { id: 1, name: 'sqlite' },
} as const

type EngineKey = keyof typeof ENGINES
type Engine = (typeof ENGINES)[EngineKey]

/** Resolve engine from the Playwright project name at test runtime */
function getEngine(): Engine {
  // test.info() is only available inside test(), so callers
  // must invoke this at the start of each test, not at module scope.
  const projectName = test.info().project.name as EngineKey
  return ENGINES[projectName] ?? ENGINES.sqlite
}

const SECTIONS = [
  { id: 0, slug: 'dashboard', name: 'Dashboard', path: '/' },
  { id: 1, slug: 'daily', name: 'Daily', path: '/daily' },
  { id: 2, slug: 'weekly', name: 'Weekly', path: '/weekly' },
  { id: 3, slug: 'monthly', name: 'Monthly', path: '/monthly' },
  { id: 4, slug: 'hourly', name: 'Hourly', path: '/hourly' },
  { id: 5, slug: 'hourofday', name: 'HourOfDay', path: '/hour-of-day' },
  { id: 6, slug: 'projects', name: 'Projects', path: '/projects' },
  { id: 7, slug: 'sessions', name: 'Sessions', path: '/sessions' },
  { id: 8, slug: 'timeline', name: 'Timeline', path: '/timeline' },
  { id: 9, slug: 'schematimeline', name: 'SchemaTimeline', path: '/schema-timeline' },
] as const

const TIME_RANGES = [
  { id: 0, value: '1', slug: '24h', label: 'Last 24 hours' },
  { id: 1, value: '3', slug: '3d', label: 'Last 3 days' },
  { id: 2, value: '7', slug: '7d', label: 'Last 7 days' },
  { id: 3, value: '14', slug: '14d', label: 'Last 14 days' },
  { id: 4, value: '30', slug: '30d', label: 'Last 30 days' },
  { id: 5, value: '90', slug: '90d', label: 'Last 90 days' },
  { id: 6, value: '180', slug: '180d', label: 'Last 180 days' },
  { id: 7, value: '0', slug: 'all', label: 'All time' },
] as const

const PROJECT_OPTIONS = [
  { id: 0, value: '', label: 'All Projects' },
  { id: 1, value: '-Users-joshpeak-play-claude-code-sessions', label: 'This Project' },
] as const

// Convenience aliases
type Section = (typeof SECTIONS)[number]
type TimeRange = (typeof TIME_RANGES)[number]
type ProjectOption = (typeof PROJECT_OPTIONS)[number]

const T_7D = TIME_RANGES[2]
const T_30D = TIME_RANGES[4]
const T_ALL = TIME_RANGES[7]
const P_ALL = PROJECT_OPTIONS[0]

// ---------------------------------------------------------------------------
// Coverage matrix — edit this to change which permutations are tested
// ---------------------------------------------------------------------------

interface CoverageEntry {
  section: Section
  timeRanges: readonly TimeRange[]
  projects: readonly ProjectOption[]
}

const SAMPLE_TIMES = [T_7D, T_ALL] as const

const COVERAGE_MATRIX: CoverageEntry[] = [
  // Dashboard: full matrix (8 × 2 = 16 tests)
  { section: SECTIONS[0], timeRanges: TIME_RANGES, projects: PROJECT_OPTIONS },
  // S1–S7: sample matrix (2 × 2 = 4 tests each = 28 tests)
  ...SECTIONS.filter((s) => s.id >= 1 && s.id <= 7).map((section) => ({
    section,
    timeRanges: SAMPLE_TIMES,
    projects: PROJECT_OPTIONS,
  })),
  // S8–S9: default only (1 × 1 = 1 test each = 2 tests)
  ...SECTIONS.filter((s) => s.id >= 8).map((section) => ({
    section,
    timeRanges: [T_30D] as readonly TimeRange[],
    projects: [P_ALL] as readonly ProjectOption[],
  })),
]

// ---------------------------------------------------------------------------
// Slug builder
// ---------------------------------------------------------------------------

  const pad = (n: number) => String(n).padStart(2, '0')                                                                                                                                                                                                                                                       

function screenshotSlug(engine: Engine, section: Section, time: TimeRange, project: ProjectOption): string {
  return `E${pad(engine.id)}_${engine.name.toUpperCase()}-S${pad(section.id)}_${section.slug.toUpperCase()}-T${pad(time.id)}_${time.slug.toUpperCase()}-P${pad(project.id)}_${project.value ? 'SINGLE' : 'ALL'}`
}

// ---------------------------------------------------------------------------
// Console log collector — captures ALL console output for .log export
// ---------------------------------------------------------------------------

import { mkdirSync, writeFileSync } from 'node:fs'
import type { Request as PlaywrightRequest } from '@playwright/test'

interface NetworkTiming {
  url: string
  method: string
  status: number | null
  /** Start time in ms, relative to when the test started (test_start_ms). */
  start_offset_ms: number
  /** Wall-clock milliseconds from request sent to response received. */
  duration_ms: number
  /** Resource type: xhr, fetch, document, script, stylesheet, image, etc. */
  resource_type: string
  /** Whether this is a backend API call (/api/...) */
  is_api: boolean
}

interface TestCollector {
  /** Write console log + network timing files paired with the screenshot */
  writeLog: (slug: string) => void
  /** Assert no real errors in the console */
  assertNoErrors: () => void
}

function collectTestIO(page: Page): TestCollector {
  // Test start timestamp — all start_offset_ms values are relative to this
  const testStart = Date.now()

  // Console capture
  const lines: string[] = []
  const errors: string[] = []

  page.on('pageerror', (err) => {
    const line = `[PAGE_ERROR] ${err.message}`
    lines.push(line)
    errors.push(err.message)
  })

  page.on('console', (msg) => {
    const level = msg.type().toUpperCase().padEnd(7)
    const line = `[${level}] ${msg.text()}`
    lines.push(line)
    if (msg.type() === 'error') errors.push(msg.text())
  })

  // Network capture — key by Request object (unique reference) to handle
  // concurrent requests to the same URL correctly.
  const network: NetworkTiming[] = []
  const pending = new Map<PlaywrightRequest, number>()

  page.on('request', (req) => {
    pending.set(req, Date.now())
  })

  page.on('requestfinished', async (req) => {
    const start = pending.get(req)
    if (start === undefined) return
    pending.delete(req)

    const res = await req.response()
    const url = req.url()
    network.push({
      url,
      method: req.method(),
      status: res ? res.status() : null,
      start_offset_ms: start - testStart,
      duration_ms: Date.now() - start,
      resource_type: req.resourceType(),
      is_api: url.includes('/api/'),
    })
  })

  page.on('requestfailed', (req) => {
    const start = pending.get(req)
    if (start === undefined) return
    pending.delete(req)
    network.push({
      url: req.url(),
      method: req.method(),
      status: null,
      start_offset_ms: start - testStart,
      duration_ms: Date.now() - start,
      resource_type: req.resourceType(),
      is_api: req.url().includes('/api/'),
    })
  })

  return {
    writeLog(slug: string) {
      const dir = 'e2e-screenshots'
      mkdirSync(dir, { recursive: true })
      writeFileSync(`${dir}/${slug}.log`, lines.join('\n') + '\n', 'utf-8')

      // Network summary — designed for both performance analysis AND
      // timeline/Gantt reconstruction. Each request has:
      //   start_offset_ms: when it began, relative to test_start_ms
      //   duration_ms:     how long it ran
      // Together these let a tool plot [start, start+duration] bars per request.
      const apiCalls = network.filter((n) => n.is_api)
      const wallClockEnd = network.reduce(
        (max, n) => Math.max(max, n.start_offset_ms + n.duration_ms),
        0,
      )
      const summary = {
        test_start_ms: testStart,
        wall_clock_duration_ms: wallClockEnd,
        total_requests: network.length,
        total_duration_ms: network.reduce((s, n) => s + n.duration_ms, 0),
        api_requests: apiCalls.length,
        api_duration_ms: apiCalls.reduce((s, n) => s + n.duration_ms, 0),
        slowest_api: [...apiCalls]
          .sort((a, b) => b.duration_ms - a.duration_ms)
          .slice(0, 5)
          .map((n) => ({
            url: n.url,
            start_offset_ms: n.start_offset_ms,
            duration_ms: n.duration_ms,
            status: n.status,
          })),
        // Sorted by start_offset so all_requests reads chronologically —
        // natural order for rendering a Gantt chart
        all_requests: [...network].sort((a, b) => a.start_offset_ms - b.start_offset_ms),
      }
      writeFileSync(
        `${dir}/${slug}.network.json`,
        JSON.stringify(summary, null, 2) + '\n',
        'utf-8',
      )
    },

    assertNoErrors() {
      const real = errors.filter(
        (e) =>
          !e.includes('act(') &&
          !e.includes('favicon') &&
          !e.includes('[vite]'),
      )
      expect(real, `Browser console errors:\n${real.join('\n')}`).toHaveLength(0)
    },
  }
}

// Legacy alias for existing call sites
const collectConsole = collectTestIO

// ---------------------------------------------------------------------------
// Wait / filter helpers
// ---------------------------------------------------------------------------

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

async function applyFilters(page: Page, time: TimeRange, project: ProjectOption): Promise<void> {
  await page.locator('select').first().selectOption(time.value)
  await waitForPageLoad(page)

  if (project.value) {
    const projectSelect = page.locator('select').nth(1)
    const exists = await projectSelect
      .locator(`option[value="${project.value}"]`)
      .count()
      .then((c) => c > 0)
      .catch(() => false)
    if (exists) {
      await projectSelect.selectOption(project.value)
      await waitForPageLoad(page)
    }
  }
}

async function verifyUrlParams(page: Page, time: TimeRange, project: ProjectOption): Promise<void> {
  const params = new URL(page.url()).searchParams
  if (time.value === '30') {
    expect(params.has('days')).toBe(false)
  } else if (params.has('days')) {
    expect(params.get('days')).toBe(time.value)
  }
  if (project.value === '') {
    expect(params.has('project')).toBe(false)
  } else if (params.has('project')) {
    expect(params.get('project')).toBe(project.value)
  }
}

// ---------------------------------------------------------------------------
// Global timeout
// ---------------------------------------------------------------------------

test.setTimeout(90000)

// =========================================================================
// PERMUTATION TESTS — generated from COVERAGE_MATRIX
//
// To add coverage: add an entry to COVERAGE_MATRIX above.
// Every entry automatically gets: navigate → filter → wait → assert → screenshot.
// =========================================================================

for (const entry of COVERAGE_MATRIX) {
  test.describe(`${entry.section.name} Filters`, () => {
    for (const time of entry.timeRanges) {
      for (const project of entry.projects) {
        // Test name uses a partial slug (without engine) — Playwright adds [sqlite]/[duckdb] suffix
        const testLabel = `S${pad(entry.section.id)}_${entry.section.slug}-T${pad(time.id)}_${time.slug}-P${pad(project.id)}: ${time.label}, ${project.label}`

        test(testLabel, async ({ page }) => {
          const engine = getEngine()
          const slug = screenshotSlug(engine, entry.section, time, project)
          const console = collectConsole(page)

          await page.goto(entry.section.path)
          await applyFilters(page, time, project)
          await verifyUrlParams(page, time, project)
          await page.screenshot({ path: `e2e-screenshots/${slug}.png`, fullPage: true })
          console.writeLog(slug)

          console.assertNoErrors()
        })
      }
    }
  })
}

// =========================================================================
// BEHAVIORAL TESTS — hand-written, not part of the permutation matrix
// =========================================================================

test.describe('Universal Filters - Core Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await waitForPageLoad(page)
  })

  test('filter dropdowns are present', async ({ page }) => {
    const console = collectConsole(page)
    await expect(page.locator('select').first()).toBeVisible()
    await expect(page.locator('select').nth(1)).toBeVisible()
    console.writeLog('behavioral-filter-dropdowns-present')
    console.assertNoErrors()
  })

  test('time range filter changes URL', async ({ page }) => {
    const console = collectConsole(page)
    await page.locator('select').first().selectOption('7')
    await waitForPageLoad(page)
    expect(page.url()).toContain('days=7')
    console.writeLog('behavioral-time-range-changes-url')
    console.assertNoErrors()
  })

  test('project filter changes URL', async ({ page }) => {
    const console = collectConsole(page)
    const sel = page.locator('select').nth(1)
    const opts = await sel.locator('option').all()
    if (opts.length > 1) {
      const val = await opts[1].getAttribute('value')
      if (val) {
        await sel.selectOption(val)
        await waitForPageLoad(page)
        expect(page.url()).toContain('project=')
      }
    }
    console.writeLog('behavioral-project-filter-changes-url')
    console.assertNoErrors()
  })

  test('filters persist across navigation', async ({ page }) => {
    const console = collectConsole(page)
    await page.locator('select').first().selectOption('7')
    await waitForPageLoad(page)
    await page.click('text=Daily')
    await waitForPageLoad(page)
    expect(page.url()).toContain('days=7')
    expect(page.url()).toContain('/daily')
    console.writeLog('behavioral-filters-persist-navigation')
    console.assertNoErrors()
  })

  test('clear filters button works', async ({ page }) => {
    const console = collectConsole(page)
    await page.locator('select').first().selectOption('7')
    await waitForPageLoad(page)
    const btn = page.locator('text=Clear filters')
    if (await btn.isVisible()) {
      await btn.click()
      await waitForPageLoad(page)
      expect(page.url()).not.toContain('days=7')
    }
    console.writeLog('behavioral-clear-filters')
    console.assertNoErrors()
  })
})

test.describe('API Filter Verification', () => {
  test('API calls include days parameter', async ({ page }) => {
    const console = collectConsole(page)
    const calls: string[] = []
    page.on('request', (r) => { if (r.url().includes('/api/')) calls.push(r.url()) })
    await page.goto('/')
    await waitForPageLoad(page)
    await page.locator('select').first().selectOption('7')
    await waitForPageLoad(page)
    expect(calls.some((u) => u.includes('days=7'))).toBe(true)
    console.writeLog('behavioral-api-includes-days')
    console.assertNoErrors()
  })

  test('API calls include project parameter', async ({ page }) => {
    const console = collectConsole(page)
    const calls: string[] = []
    page.on('request', (r) => { if (r.url().includes('/api/')) calls.push(r.url()) })
    await page.goto('/')
    await waitForPageLoad(page)
    const sel = page.locator('select').nth(1)
    const opts = await sel.locator('option').all()
    if (opts.length > 1) {
      const val = await opts[1].getAttribute('value')
      if (val) {
        await sel.selectOption(val)
        await waitForPageLoad(page)
        expect(calls.some((u) => u.includes('project='))).toBe(true)
      }
    }
    console.writeLog('behavioral-api-includes-project')
    console.assertNoErrors()
  })
})

test.describe('Dynamic Project List', () => {
  test('project list reflects time range', async ({ page }) => {
    const console = collectConsole(page)
    await page.goto('/')
    await waitForPageLoad(page)
    await page.locator('select').first().selectOption('1')
    await waitForPageLoad(page)
    const count = await page.locator('select').nth(1).locator('option').count()
    expect(count).toBeGreaterThanOrEqual(1)
    console.writeLog('behavioral-dynamic-project-list')
    console.assertNoErrors()
  })
})

test.describe('Timeline Project Requirement', () => {
  test('shows message when no project selected', async ({ page }) => {
    const console = collectConsole(page)
    await page.goto('/timeline')
    await waitForPageLoad(page)
    const text = await page.innerText('body')
    expect(text.toLowerCase()).toContain('select a project')
    console.writeLog('behavioral-timeline-no-project')
    console.assertNoErrors()
  })

  test('shows data when project selected', async ({ page }) => {
    const console = collectConsole(page)
    await page.goto('/timeline')
    await waitForPageLoad(page)
    const sel = page.locator('select').nth(1)
    const opts = await sel.locator('option').all()
    if (opts.length > 1) {
      const val = await opts[1].getAttribute('value')
      if (val) {
        await sel.selectOption(val)
        await waitForPageLoad(page)
        await page.waitForFunction(
          () => {
            const t = document.body.innerText
            return !t.includes('Loading') && (t.includes('Timeline') || t.includes('No events'))
          },
          { timeout: 45000 },
        ).catch(() => {})
        const text = await page.innerText('body')
        expect(text).toMatch(/Timeline|No events/)
      }
    }
    console.writeLog('behavioral-timeline-with-project')
    console.assertNoErrors()
  })
})

test.describe('Sessions Navigation', () => {
  test('sessions list loads', async ({ page }) => {
    const engine = getEngine()
    const slug = `E${pad(engine.id)}_${engine.name}-sessions-list`
    const console = collectConsole(page)
    await page.goto('/sessions')
    await waitForPageLoad(page)
    await page.screenshot({ path: `e2e-screenshots/${slug}.png`, fullPage: true })
    console.writeLog(slug)
    console.assertNoErrors()
  })

  test('project → session detail navigation', async ({ page }) => {
    const engine = getEngine()
    const ePrefix = `E${pad(engine.id)}_${engine.name}`
    const console = collectConsole(page)
    await page.goto('/sessions')
    await waitForPageLoad(page)

    const projectLink = page.locator('a[href*="/sessions/"]').first()
    if (await projectLink.isVisible()) {
      await projectLink.click()
      await waitForPageLoad(page)
      expect(page.url()).toMatch(/\/sessions\/[^/]+$/)

      const projSlug = `${ePrefix}-project-sessions`
      await page.screenshot({ path: `e2e-screenshots/${projSlug}.png`, fullPage: true })
      console.writeLog(projSlug)

      const sessionLink = page.locator('a[href*="/sessions/"]').first()
      if (await sessionLink.isVisible()) {
        await sessionLink.click()
        await waitForPageLoad(page)
        expect(page.url()).toMatch(/\/sessions\/[^/]+\/[^/]+/)

        const detailSlug = `${ePrefix}-session-detail`
        await page.screenshot({ path: `e2e-screenshots/${detailSlug}.png`, fullPage: true })
        console.writeLog(detailSlug)
      }
    }
    console.assertNoErrors()
  })
})
