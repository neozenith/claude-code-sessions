import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ClaimsExplorerView } from './ClaimsExplorer'
import { ThemeProvider } from '../contexts/ThemeContext'
import type { Claim, ClaimRollup, CoveragePivot } from '../lib/api-client'

// jsdom (as configured here) doesn't implement matchMedia or a writable
// localStorage; ThemeProvider — pulled in transitively by the
// CoverageHeatmap's usePlotlyTheme — reads both. Shim minimal stubs so the
// provider can resolve the system theme. This is environment shimming, not
// behavior mocking — the component code is exercised for real.
if (!window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList
}
if (typeof window.localStorage === 'undefined' || window.localStorage === null) {
  const store = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      get length() {
        return store.size
      },
    },
  })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function LocationProbe() {
  const loc = useLocation()
  return createElement('div', { 'data-testid': 'loc' }, loc.search)
}

const currentParam = (key: string): string | null =>
  new URLSearchParams(screen.getByTestId('loc').textContent ?? '').get(key)

const claim = (text: string, count: number, sessions: string[] = []): Claim => ({
  claim: text,
  count,
  sessions,
})

const summarised = (
  tasks: Claim[],
  patterns: Claim[],
  decisions: Claim[],
  extra: { failure_count?: number; failed_sessions?: string[] } = {},
): ClaimRollup => ({
  status: 'summarised',
  scope_path: 'clients/acme',
  grain: 'month',
  bucket: '2026-05',
  model: 'qwen3',
  lenses: { tasks, patterns, decisions_values: decisions, learnings: [] },
  failure_count: extra.failure_count ?? 0,
  failed_sessions: extra.failed_sessions ?? [],
})

function renderView(
  props: Partial<Parameters<typeof ClaimsExplorerView>[0]>,
  entries: string[] = ['/claims'],
) {
  return render(
    createElement(
      ThemeProvider,
      null,
      createElement(
        MemoryRouter,
        { initialEntries: entries },
        createElement(ClaimsExplorerView, {
          rollup: null,
          buckets: [],
          models: [],
          childScopes: [],
          coverage: null,
          pivot: null,
          loading: false,
          scopePath: '',
          pinned: false,
          days: 30,
          ...props,
        }),
        createElement(LocationProbe),
      ),
    ),
  )
}

describe('ClaimsExplorerView — not_summarised empty state (ADR8.2)', () => {
  it('renders the empty state and no lens cards when not summarised', () => {
    renderView({ rollup: { status: 'not_summarised' } })
    expect(screen.getByTestId('claims-empty')).toBeTruthy()
    expect(screen.queryByTestId('claims-lens-tasks')).toBeNull()
    expect(screen.queryByTestId('claims-lens-patterns')).toBeNull()
    expect(screen.queryByTestId('claims-lens-decisions')).toBeNull()
  })

  it('renders the three lens cards (and no empty state) when summarised', () => {
    renderView({
      rollup: summarised([claim('t1', 1)], [claim('p1', 1)], [claim('d1', 1)]),
    })
    expect(screen.getByTestId('claims-lens-tasks')).toBeTruthy()
    expect(screen.getByTestId('claims-lens-patterns')).toBeTruthy()
    expect(screen.getByTestId('claims-lens-decisions')).toBeTruthy()
    expect(screen.queryByTestId('claims-empty')).toBeNull()
  })
})

describe('ClaimsExplorerView — ranked claims + counts (ADR8.2)', () => {
  it('sorts claims by count descending within a lens', () => {
    renderView({
      rollup: summarised(
        [claim('low', 1), claim('high', 9), claim('mid', 4)],
        [],
        [],
      ),
    })
    const tasksCard = screen.getByTestId('claims-lens-tasks')
    const items = tasksCard.querySelectorAll('[data-testid="claim-item"]')
    const texts = Array.from(items).map((el) => el.textContent ?? '')
    // Ranked high (9) → mid (4) → low (1).
    expect(texts[0]).toContain('high')
    expect(texts[0]).toContain('(9×)')
    expect(texts[1]).toContain('mid')
    expect(texts[2]).toContain('low')
  })

  it('renders a count badge and provenance session links per claim', () => {
    renderView({
      rollup: summarised([claim('a claim', 3, ['sess-aaaaaaaa', 'sess-bbbbbbbb'])], [], []),
    })
    const tasksCard = screen.getByTestId('claims-lens-tasks')
    expect(tasksCard.querySelector('[data-testid="claim-count"]')?.textContent).toBe('(3×)')
    const links = tasksCard.querySelectorAll('[data-testid="claim-session-link"]')
    expect(links.length).toBe(2)
    expect((links[0] as HTMLAnchorElement).getAttribute('href')).toContain('session=sess-aaaaaaaa')
  })

  it('shows a "No claims." placeholder for an empty lens', () => {
    renderView({ rollup: summarised([], [], []) })
    const tasksCard = screen.getByTestId('claims-lens-tasks')
    expect(tasksCard.textContent).toContain('No claims.')
    expect(tasksCard.querySelectorAll('[data-testid="claim-item"]').length).toBe(0)
  })
})

describe('ClaimsExplorerView — failures badge (CR5)', () => {
  it('renders the failure badge with count and links the failed sessions', () => {
    renderView({
      rollup: summarised([claim('t', 1)], [], [], {
        failure_count: 2,
        failed_sessions: ['fail-1111', 'fail-2222'],
      }),
    })
    expect(screen.getByTestId('claims-failure-badge').textContent).toContain('2 extraction failures')
    expect(screen.getAllByTestId('claims-failed-session').length).toBe(2)
  })

  it('omits the failures block when failure_count is 0', () => {
    renderView({ rollup: summarised([claim('t', 1)], [], []) })
    expect(screen.queryByTestId('claims-failures')).toBeNull()
  })
})

describe('ClaimsExplorerView — URL state (ADR8.1)', () => {
  it('grain/bucket/model selects write URL params and omit defaults', () => {
    renderView(
      {
        models: [
          { model: 'qwen3', has_claims: true },
          { model: 'gemma', has_claims: true },
        ],
        buckets: [{ bucket: '2026-05', n_claims: 5, total_count: 9 }],
      },
      ['/claims?grain=month'],
    )

    fireEvent.change(screen.getByTestId('claims-grain-select'), { target: { value: 'week' } })
    expect(currentParam('grain')).toBe('week')

    // Switching back to the default grain omits the param.
    fireEvent.change(screen.getByTestId('claims-grain-select'), { target: { value: 'month' } })
    expect(currentParam('grain')).toBeNull()

    fireEvent.change(screen.getByTestId('claims-bucket-select'), { target: { value: '2026-05' } })
    expect(currentParam('bucket')).toBe('2026-05')

    fireEvent.change(screen.getByTestId('claims-model-select'), { target: { value: 'gemma' } })
    expect(currentParam('model')).toBe('gemma')
  })
})

describe('ClaimsExplorerView — cache summarisation panel (CR5)', () => {
  it('renders the coverage panel when coverage is provided', () => {
    renderView({
      coverage: {
        model: 'qwen3',
        overall: { total: 10, summarised: 6, failed: 1, pending: 3, pct_complete: 60 },
        projects: [
          { project_id: 'p1', scope_path: 'play/p1', domain: 'play', total: 10, summarised: 6, failed: 1, pending: 3, pct_complete: 60 },
        ],
      },
    })
    expect(screen.getByTestId('cache-summarisation')).toBeTruthy()
    expect(screen.getByTestId('coverage-overall-pct').textContent).toContain('60.0%')
  })

  it('omits the coverage panel when coverage is null', () => {
    renderView({ coverage: null })
    expect(screen.queryByTestId('cache-summarisation')).toBeNull()
  })
})

describe('ClaimsExplorerView — model detail selector (CR5)', () => {
  it('lists all models and labels the ones with no claims', () => {
    renderView({
      models: [
        { model: 'qwen3', has_claims: true },
        { model: 'Llama-3.1-8B', has_claims: false },
      ],
    })
    const select = screen.getByTestId('claims-model-select') as HTMLSelectElement
    const labels = Array.from(select.options).map((o) => o.textContent)
    expect(labels).toContain('qwen3')
    expect(labels).toContain('Llama-3.1-8B (no data)')
  })

  it('selecting a no-data model still drives the view (writes ?model=)', () => {
    renderView({
      models: [
        { model: 'qwen3', has_claims: true },
        { model: 'Llama-3.1-8B', has_claims: false },
      ],
      rollup: { status: 'not_summarised' },
    })
    fireEvent.change(screen.getByTestId('claims-model-select'), {
      target: { value: 'Llama-3.1-8B' },
    })
    expect(currentParam('model')).toBe('Llama-3.1-8B')
    // No-data model shows the not_summarised empty state, not lens cards.
    expect(screen.getByTestId('claims-empty')).toBeTruthy()
  })
})

describe('ClaimsExplorerView — sortable lens columns (CR5)', () => {
  it('default order is count descending', () => {
    renderView({
      rollup: summarised([claim('low', 1), claim('high', 9), claim('mid', 4)], [], []),
    })
    const items = screen
      .getByTestId('claims-lens-tasks')
      .querySelectorAll('[data-testid="claim-item"]')
    const texts = Array.from(items).map((el) => el.textContent ?? '')
    expect(texts[0]).toContain('high')
    expect(texts[2]).toContain('low')
  })

  it('clicking the count header flips to ascending', () => {
    renderView({
      rollup: summarised([claim('low', 1), claim('high', 9), claim('mid', 4)], [], []),
    })
    fireEvent.click(screen.getByTestId('sort-tasks-count'))
    const items = screen
      .getByTestId('claims-lens-tasks')
      .querySelectorAll('[data-testid="claim-item"]')
    const texts = Array.from(items).map((el) => el.textContent ?? '')
    // Ascending: low (1) → mid (4) → high (9).
    expect(texts[0]).toContain('low')
    expect(texts[2]).toContain('high')
  })

  it('clicking the text header sorts by claim text ascending', () => {
    renderView({
      rollup: summarised([claim('banana', 1), claim('apple', 9), claim('cherry', 4)], [], []),
    })
    fireEvent.click(screen.getByTestId('sort-tasks-claim'))
    const items = screen
      .getByTestId('claims-lens-tasks')
      .querySelectorAll('[data-testid="claim-item"]')
    const texts = Array.from(items).map((el) => el.textContent ?? '')
    expect(texts[0]).toContain('apple')
    expect(texts[1]).toContain('banana')
    expect(texts[2]).toContain('cherry')
  })

  it('sort is per-lens — sorting tasks does not reorder patterns', () => {
    renderView({
      rollup: summarised(
        [claim('t-low', 1), claim('t-high', 9)],
        [claim('p-low', 1), claim('p-high', 9)],
        [],
      ),
    })
    fireEvent.click(screen.getByTestId('sort-tasks-count')) // tasks → asc
    const patternsTexts = Array.from(
      screen
        .getByTestId('claims-lens-patterns')
        .querySelectorAll('[data-testid="claim-item"]'),
    ).map((el) => el.textContent ?? '')
    // Patterns still default count-desc.
    expect(patternsTexts[0]).toContain('p-high')
  })
})

describe('ClaimsExplorerView — global filters: window + project pin (CR5)', () => {
  it('window note describes the days-windowed aggregate when no bucket is chosen', () => {
    renderView({ days: 7, scopePath: 'play/proj' })
    const note = screen.getByTestId('claims-window-note').textContent ?? ''
    expect(note).toContain('all month claims')
    expect(note).toContain('the last 7 days')
  })

  it('window note says "all time" when days is 0 (All time)', () => {
    renderView({ days: 0 })
    expect(screen.getByTestId('claims-window-note').textContent ?? '').toContain('all time')
  })

  it('window note switches to a drill-down label when a bucket is selected', () => {
    renderView({ days: 30 }, ['/claims?bucket=2026-05'])
    const note = screen.getByTestId('claims-window-note').textContent ?? ''
    expect(note).toContain('2026-05')
    expect(note).toContain('drill-down')
  })

  it('hard-pin renders a static (pinned) breadcrumb with no drill links', () => {
    renderView({ pinned: true, scopePath: 'clients/acme', childScopes: [
      { scope_path: 'clients/acme/sub', scope_depth: 3 },
    ] })
    expect(screen.getByTestId('scope-breadcrumb-pinned')).toBeTruthy()
    // Crumbs are plain text, not navigable links, and child drill-downs are hidden.
    expect(screen.queryByTestId('scope-child')).toBeNull()
    expect(screen.getByTestId('scope-breadcrumb-pinned').textContent).toContain('pinned')
  })

  it('unpinned breadcrumb keeps navigable crumb links', () => {
    renderView({ pinned: false, scopePath: 'clients/acme' })
    expect(screen.queryByTestId('scope-breadcrumb-pinned')).toBeNull()
    // The root crumb is a real link in the navigable breadcrumb.
    expect(screen.getByTestId('scope-crumb-root').tagName).toBe('A')
  })
})

const PIVOT: CoveragePivot = {
  model: 'qwen3',
  grain: 'month',
  scopes: ['clients/acme', 'clients/beta'],
  buckets: ['2026-04', '2026-05'],
  cells: [
    { scope_path: 'clients/acme', bucket: '2026-05', sessions: 4, claims: 12, failures: 0, status: 'done' },
    { scope_path: 'clients/beta', bucket: '2026-04', sessions: 2, claims: 0, failures: 1, status: 'failed' },
  ],
}

describe('ClaimsExplorerView — coverage heatmap (CR5)', () => {
  it('renders the heatmap card when pivot data is provided', () => {
    renderView({ pivot: PIVOT })
    expect(screen.getByTestId('coverage-heatmap')).toBeTruthy()
  })

  it('omits the heatmap when pivot is null or empty', () => {
    renderView({ pivot: null })
    expect(screen.queryByTestId('coverage-heatmap')).toBeNull()

    cleanup()
    renderView({ pivot: { model: 'm', grain: 'month', scopes: [], buckets: [], cells: [] } })
    expect(screen.queryByTestId('coverage-heatmap')).toBeNull()
  })
})

describe('ClaimsExplorerView — reindex trigger (CR5)', () => {
  it('POSTs reindex then polls status and reflects it', async () => {
    const calls: string[] = []
    const jsonResponse = (body: unknown) =>
      ({ ok: true, status: 200, json: async () => body }) as Response

    const fetchStub = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      if (url.includes('/claims/reindex/status')) {
        return jsonResponse({
          state: 'done',
          scope_path: 'clients/acme',
          grain: 'month',
          model: 'qwen3',
          sessions_total: 5,
          sessions_done: 5,
          failures: 1,
          rollups_written: 3,
          message: 'complete',
          error: null,
        })
      }
      // POST /claims/reindex
      return jsonResponse({ state: 'running', already_running: false, message: 'started' })
    })
    vi.stubGlobal('fetch', fetchStub)

    renderView(
      { models: [{ model: 'qwen3', has_claims: true }], scopePath: 'clients/acme' },
      ['/claims?path=clients/acme&model=qwen3'],
    )

    fireEvent.click(screen.getByTestId('reindex-button'))

    // The POST fired with the current slice params.
    await waitFor(() => {
      expect(calls.some((u) => u.includes('/claims/reindex?'))).toBe(true)
    })
    const postUrl = calls.find((u) => u.includes('/claims/reindex?')) ?? ''
    expect(postUrl).toContain('path=clients%2Facme')
    expect(postUrl).toContain('model=qwen3')

    // Status poll resolves to "done · 5/5 sessions · 1 failures".
    await waitFor(() => {
      const status = screen.getByTestId('reindex-status').textContent ?? ''
      expect(status).toContain('done')
      expect(status).toContain('5/5')
      expect(status).toContain('1 failures')
    })
  })
})
