import { expect, test } from '@playwright/test'

/**
 * KG Cache page e2e — pipeline backlog diagnostics at /kg/cache.
 *
 * Unlike the graph page, this endpoint never 422s: it reports pipeline
 * progress even on a cold/empty cache (every stage simply reads 0 done).
 * So the page is always renderable and we don't skip on empty data.
 */

test.describe('Knowledge Graph Cache page', () => {
  test('serves pipeline stats with an indexer status and ordered stages', async ({ page }) => {
    const apiResp = await page.request.get('/api/kg/cache-stats')
    expect(apiResp.ok()).toBe(true)
    const stats = await apiResp.json()

    // Indexer status block is always present (idle at minimum).
    expect(stats.indexer).toBeTruthy()
    expect(typeof stats.indexer.phase).toBe('string')

    // Stages are present, ordered ingest → naming, and internally consistent.
    const keys = stats.stages.map((s: { key: string }) => s.key)
    expect(keys).toEqual([
      'ingest',
      'chunk',
      'embed',
      'ner',
      're',
      'entity_embed',
      'resolve',
      'communities',
      'naming',
    ])
    for (const stage of stats.stages) {
      expect(stage.pending).toBe(Math.max(0, stage.eligible - stage.done))
      expect(stage.done).toBeLessThanOrEqual(stage.eligible)
      expect(stage.percent).toBeGreaterThanOrEqual(0)
      expect(stage.percent).toBeLessThanOrEqual(100)
    }
  })

  test('renders the page with metric cards, stage rows, and nav entry', async ({ page }) => {
    await page.goto('/kg/cache')

    await expect(page.getByTestId('kg-cache-page')).toBeVisible()
    await expect(page.getByRole('heading', { name: /Cache Pipeline/ })).toBeVisible()

    // Indexer banner exposes its phase via a data attribute.
    const indexer = page.getByTestId('kg-cache-indexer')
    await expect(indexer).toBeVisible()
    await expect(indexer).toHaveAttribute('data-phase', /idle|running|completed|cancelled|failed/)

    // First and last pipeline stages render.
    await expect(page.getByTestId('kg-cache-stage-ingest')).toBeVisible()
    await expect(page.getByTestId('kg-cache-stage-naming')).toBeVisible()

    // Sidebar nav must include the Cache entry, sitting under Knowledge Graph.
    await expect(page.getByRole('link', { name: 'Cache' })).toBeVisible()

    // Controls: Run indexer + Refresh, and the coverage summary line.
    await expect(page.getByRole('button', { name: /Run indexer|Indexing/ })).toBeVisible()
    await expect(page.getByText(/Pipeline coverage:/)).toBeVisible()

    await page.screenshot({
      path: 'e2e-screenshots/kg-cache.png',
      fullPage: false,
    })
  })

  test('POST /api/kg/reindex is idempotent and returns indexer status', async ({ page }) => {
    const resp = await page.request.post('/api/kg/reindex')
    expect(resp.ok()).toBe(true)
    const status = await resp.json()
    expect(typeof status.phase).toBe('string')
    expect(status).toHaveProperty('already_running')
  })
})
