import { test, expect, Page } from '@playwright/test'

/**
 * Search page E2E tests.
 *
 * Verifies the /search view that is backed by the events_fts SQLite FTS5
 * index. Focuses on behaviors specific to this page:
 *
 *   - Empty state when no query is in the URL.
 *   - Debounced URL sync (typing pushes the query into ?q=).
 *   - Global filters scope results (days, project).
 *   - Clicking a result navigates into the session detail view.
 *
 * Notes:
 *   - These tests don't assert on specific *content* matches because the
 *     real JSONL corpus changes over time. They assert on structural
 *     invariants — the input exists, the URL updates, a result list
 *     renders when hits exist, an empty-state card renders when it
 *     doesn't.
 *   - Debounce is 300ms in the component; we wait 500ms to be safe.
 */

// A search term that should appear somewhere in a populated local
// corpus. "claude" is a pragmatic pick — self-reflective messages
// mention it often. If the corpus is genuinely empty this still
// exercises the no-results path cleanly.
const COMMON_TERM = 'claude'
const DEBOUNCE_WAIT_MS = 500

test.setTimeout(60000)

async function waitForSearchReady(page: Page): Promise<void> {
  // Initial page mount — the input is autoFocused so its presence is
  // the earliest signal the page has hydrated.
  await page.waitForSelector('[data-testid="search-input"]', { timeout: 15000 })
}

async function typeQuery(page: Page, text: string): Promise<void> {
  const input = page.locator('[data-testid="search-input"]')
  await input.fill(text)
  // Wait for debounce → URL sync → fetch → results render. We poll for
  // either a results list OR a no-results empty state, whichever appears.
  await page.waitForTimeout(DEBOUNCE_WAIT_MS)
  await page
    .waitForFunction(
      () =>
        document.querySelector('[data-testid="search-results"]') !== null ||
        document.querySelector('[data-testid="search-no-results"]') !== null ||
        document.querySelector('[data-testid="search-loading"]') === null,
      { timeout: 10000 },
    )
    .catch(() => {})
}

test.describe('Search page', () => {
  test('empty state renders when no ?q= param is present', async ({ page }) => {
    await page.goto('/search')
    await waitForSearchReady(page)

    // The instructional empty-state card shows, and the results grid
    // is not present.
    await expect(page.locator('[data-testid="search-empty"]')).toBeVisible()
    await expect(page.locator('[data-testid="search-results"]')).toHaveCount(0)

    // The URL should not have a ?q= param.
    const url = new URL(page.url())
    expect(url.searchParams.has('q')).toBe(false)
  })

  test('typing a query debounces into ?q= and fetches results', async ({ page }) => {
    await page.goto('/search')
    await waitForSearchReady(page)

    await typeQuery(page, COMMON_TERM)

    // After debounce, the URL reflects the query.
    const url = new URL(page.url())
    expect(url.searchParams.get('q')).toBe(COMMON_TERM)

    // Either results or the no-results card is visible — both are
    // acceptable, only the empty-state ("type a query above") is not.
    await expect(page.locator('[data-testid="search-empty"]')).toHaveCount(0)
    const hasResults = (await page.locator('[data-testid="search-results"]').count()) > 0
    const hasNoResults = (await page.locator('[data-testid="search-no-results"]').count()) > 0
    expect(hasResults || hasNoResults).toBe(true)
  })

  test('deep-link with ?q= preloads the query into the input', async ({ page }) => {
    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}`)
    await waitForSearchReady(page)

    // The input reflects the URL query.
    await expect(page.locator('[data-testid="search-input"]')).toHaveValue(COMMON_TERM)
  })

  test('clearing the input removes ?q= and returns to empty state', async ({ page }) => {
    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}`)
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS)

    await page.locator('[data-testid="search-input"]').fill('')
    await page.waitForTimeout(DEBOUNCE_WAIT_MS)

    // URL no longer has ?q=
    const url = new URL(page.url())
    expect(url.searchParams.has('q')).toBe(false)

    // Empty-state card is back.
    await expect(page.locator('[data-testid="search-empty"]')).toBeVisible()
  })

  test('time-range filter narrows results (URL carries days=)', async ({ page }) => {
    // Deep-link with a query AND a tight 7-day window. The backend is
    // responsible for applying the filter; from the frontend side the
    // observable effect is that the URL carries `days=7` and the fetch
    // URL forwarded to /api/search also carries it.
    let apiRequestSeen = false
    page.on('request', (req) => {
      const url = req.url()
      if (url.includes('/api/search') && url.includes('days=7')) {
        apiRequestSeen = true
      }
    })

    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}&days=7`)
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    // URL retains both params.
    const url = new URL(page.url())
    expect(url.searchParams.get('q')).toBe(COMMON_TERM)
    expect(url.searchParams.get('days')).toBe('7')

    // The frontend forwarded days=7 to the backend.
    expect(apiRequestSeen).toBe(true)
  })

  test('project filter scopes the search to a single project_id', async ({ page }) => {
    // Same idea as the days filter — confirm the frontend forwards the
    // project selector into the /api/search call.
    let apiUrlSeen: string | null = null
    page.on('request', (req) => {
      const u = req.url()
      if (u.includes('/api/search') && u.includes('q=')) {
        apiUrlSeen = u
      }
    })

    // Load dashboard first to get a real project_id from the sidebar.
    // The project list is populated by an async /api/projects fetch so we
    // poll until the select has at least one real (non-empty-value)
    // option before reading it.
    await page.goto('/')
    await page.waitForSelector('select', { timeout: 15000 })
    const projectSelect = page.locator('select').nth(1)
    await page
      .waitForFunction(
        () => {
          const selects = document.querySelectorAll('select')
          const proj = selects[1] as HTMLSelectElement | undefined
          if (!proj) return false
          return Array.from(proj.options).some((o) => o.value !== '')
        },
        { timeout: 10000 },
      )
      .catch(() => {})
    const projectOptions = await projectSelect
      .locator('option')
      .evaluateAll((opts) =>
        opts
          .map((o) => (o as HTMLOptionElement).value)
          .filter((v) => v !== ''),
      )

    if (projectOptions.length === 0) {
      test.skip(true, 'No projects available in current corpus — cannot scope search')
      return
    }

    const firstProject = projectOptions[0]
    await page.goto(
      `/search?q=${encodeURIComponent(COMMON_TERM)}&project=${encodeURIComponent(firstProject)}`,
    )
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    // URL carries project=.
    const url = new URL(page.url())
    expect(url.searchParams.get('project')).toBe(firstProject)

    // The frontend forwarded project= to the backend.
    expect(apiUrlSeen).not.toBeNull()
    expect(apiUrlSeen).toContain(`project=${encodeURIComponent(firstProject)}`)
  })

  test('clicking a result navigates to the session detail view', async ({ page }) => {
    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}`)
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    const resultRows = page.locator('[data-testid="search-result-row"]')
    const count = await resultRows.count()
    if (count === 0) {
      test.skip(true, 'Corpus has no matches for this term; cannot test navigation')
      return
    }

    await resultRows.first().click()
    // Session detail routes under /sessions/<project>/<session>
    await expect(page).toHaveURL(/\/sessions\/[^/]+\/[^/]+/, { timeout: 10000 })
  })

  test('message-kind dropdown is visible and defaults to "All messages"', async ({ page }) => {
    await page.goto('/search')
    await waitForSearchReady(page)

    const kindSelect = page.locator('[data-testid="msg-kind-filter"]')
    await expect(kindSelect).toBeVisible()
    await expect(kindSelect).toHaveValue('')
  })

  test('selecting a kind writes ?msg= and forwards msg_kind to the API', async ({ page }) => {
    // Capture /api/search requests so we can assert the msg_kind param is
    // forwarded after the user picks a kind. We grab the *last* search
    // request observed because the initial fetch (pre-selection) will
    // not carry msg_kind.
    const apiUrls: string[] = []
    page.on('request', (req) => {
      const u = req.url()
      if (u.includes('/api/search') && u.includes('q=')) {
        apiUrls.push(u)
      }
    })

    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}`)
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    await page.locator('[data-testid="msg-kind-filter"]').selectOption('human')
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    // URL reflects the kind selection.
    const url = new URL(page.url())
    expect(url.searchParams.get('msg')).toBe('human')
    expect(url.searchParams.get('q')).toBe(COMMON_TERM)

    // The most recent API request carries msg_kind=human.
    const lastApi = apiUrls[apiUrls.length - 1]
    expect(lastApi).toContain('msg_kind=human')
  })

  test('deep-link with ?msg=human selects the dropdown on load', async ({ page }) => {
    await page.goto(
      `/search?q=${encodeURIComponent(COMMON_TERM)}&msg=assistant_text`,
    )
    await waitForSearchReady(page)
    await expect(page.locator('[data-testid="msg-kind-filter"]')).toHaveValue(
      'assistant_text',
    )
  })

  test('result cards show a session_id badge', async ({ page }) => {
    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}`)
    await waitForSearchReady(page)

    // Wait for results *or* an empty state — whichever resolves first.
    // A fixed waitForTimeout races the fetch when the backend is slow
    // under parallel test load.
    await page
      .waitForFunction(
        () =>
          document.querySelector('[data-testid="search-results"]') !== null ||
          document.querySelector('[data-testid="search-no-results"]') !== null,
        { timeout: 15000 },
      )
      .catch(() => {})

    const rows = page.locator('[data-testid="search-result-row"]')
    const count = await rows.count()
    if (count === 0) {
      test.skip(true, 'Corpus has no matches — cannot verify session_id badge')
      return
    }
    // Every visible result row has exactly one session_id badge inside it.
    for (let i = 0; i < count; i++) {
      const row = rows.nth(i)
      const badge = row.locator('[data-testid="search-result-session-id"]')
      await expect(badge).toBeVisible()
      // Badge text is either a short hex slug or "—" — both non-empty.
      const text = (await badge.textContent())?.trim() ?? ''
      expect(text.length).toBeGreaterThan(0)
    }
  })

  test('result link forwards the msg filter into session-detail URL', async ({ page }) => {
    await page.goto(
      `/search?q=${encodeURIComponent(COMMON_TERM)}&msg=human`,
    )
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    const rows = page.locator('[data-testid="search-result-row"]')
    const count = await rows.count()
    if (count === 0) {
      test.skip(true, 'Corpus has no human-kind matches — cannot verify link forwarding')
      return
    }
    const href = await rows.first().getAttribute('href')
    expect(href).toBeTruthy()
    expect(href).toContain('msg=human')
  })

  // ---- search mode (keyword vs semantic) ----------------------------

  test('mode toggle is visible and defaults to keyword', async ({ page }) => {
    await page.goto('/search')
    await waitForSearchReady(page)

    const toggle = page.locator('[data-testid="search-mode-toggle"]')
    await expect(toggle).toBeVisible()
    const keywordBtn = page.locator('[data-testid="search-mode-keyword"]')
    const semanticBtn = page.locator('[data-testid="search-mode-semantic"]')
    await expect(keywordBtn).toHaveAttribute('aria-selected', 'true')
    await expect(semanticBtn).toHaveAttribute('aria-selected', 'false')
  })

  test('clicking Semantic writes ?mode=semantic and forwards to API', async ({ page }) => {
    const apiUrls: string[] = []
    page.on('request', (req) => {
      const u = req.url()
      if (u.includes('/api/search') && u.includes('q=')) {
        apiUrls.push(u)
      }
    })

    await page.goto(`/search?q=${encodeURIComponent(COMMON_TERM)}`)
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    await page.locator('[data-testid="search-mode-semantic"]').click()
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    // URL reflects the semantic mode.
    const url = new URL(page.url())
    expect(url.searchParams.get('mode')).toBe('semantic')

    // The most recent API request carries mode=semantic.
    const lastApi = apiUrls[apiUrls.length - 1]
    expect(lastApi).toContain('mode=semantic')
    expect(lastApi).toContain('q=')
  })

  test('clicking Keyword from semantic mode drops ?mode= from URL', async ({ page }) => {
    await page.goto(
      `/search?q=${encodeURIComponent(COMMON_TERM)}&mode=semantic`,
    )
    await waitForSearchReady(page)
    await page.waitForTimeout(DEBOUNCE_WAIT_MS + 500)

    await page.locator('[data-testid="search-mode-keyword"]').click()
    await page.waitForTimeout(DEBOUNCE_WAIT_MS)

    // Keyword is default — omit from URL for clean links.
    const url = new URL(page.url())
    expect(url.searchParams.has('mode')).toBe(false)
    expect(url.searchParams.get('q')).toBe(COMMON_TERM)
  })

  test('deep-link ?mode=semantic selects the Semantic tab on load', async ({ page }) => {
    await page.goto('/search?mode=semantic')
    await waitForSearchReady(page)

    await expect(page.locator('[data-testid="search-mode-semantic"]')).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await expect(page.locator('[data-testid="search-mode-keyword"]')).toHaveAttribute(
      'aria-selected',
      'false',
    )
  })
})
