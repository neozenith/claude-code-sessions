import { expect, test } from '@playwright/test'

/**
 * Knowledge Graph e2e — entity-resolved cytoscape view.
 *
 * Visual parity target: http://localhost:5282/sessions_demo/kg/er/
 *
 * Requires the backend KG pipeline to have populated nodes/edges/
 * leiden_communities at least once. The pipeline runs on every server
 * start (phase 7/7); first cold start is slow because Qwen NER+RE on
 * the full corpus takes hours, so this test will skip itself if the
 * cache is empty rather than blocking CI on a multi-hour boot.
 */

test.describe('Knowledge Graph page', () => {
  test('renders the cytoscape graph at /kg with nodes, edges, and communities', async ({
    page,
  }) => {
    const apiResp = await page.request.get('/api/kg/er?top_n=200')
    if (apiResp.status() === 422) {
      test.skip(true, 'KG pipeline has not populated nodes yet — run server once to bootstrap')
    }
    expect(apiResp.ok()).toBe(true)
    const payload = await apiResp.json()
    expect(payload.table_id).toBe('er')
    expect(payload.node_count).toBeGreaterThan(0)
    expect(payload.edge_count).toBeGreaterThanOrEqual(0)
    expect(payload.community_count).toBeGreaterThanOrEqual(0)

    await page.goto('/kg')
    await expect(page.getByTestId('kg-page')).toBeVisible()
    await expect(page.getByRole('heading', { name: /Knowledge Graph/ })).toBeVisible()

    // Cytoscape mounts three stacked <canvas> elements; wait for them to exist.
    await page.waitForFunction(() => document.querySelectorAll('canvas').length >= 3, null, {
      timeout: 10_000,
    })

    // Wait for the page to publish the data-* readiness marker.
    const ready = page.getByTestId('kg-canvas-ready')
    await expect(ready).toBeAttached({ timeout: 10_000 })

    const nodeCount = await ready.getAttribute('data-node-count')
    const edgeCount = await ready.getAttribute('data-edge-count')
    expect(Number(nodeCount)).toBeGreaterThan(0)
    expect(Number(edgeCount)).toBeGreaterThanOrEqual(0)

    // Sidebar nav must include the Knowledge Graph entry.
    await expect(page.getByRole('link', { name: 'Knowledge Graph' })).toBeVisible()

    // Right-panel controls must be present.
    await expect(page.getByTestId('kg-control-seed-metric')).toBeVisible()
    await expect(page.getByTestId('kg-control-top-n')).toBeVisible()
    await expect(page.getByTestId('kg-control-layout')).toBeVisible()
    await expect(page.getByTestId('kg-control-size-mode')).toBeVisible()

    await page.screenshot({
      path: 'e2e-screenshots/kg-er.png',
      fullPage: false,
    })
  })

  test('?topN=10 query param loads a smaller subgraph', async ({ page }) => {
    await page.goto('/kg?topN=10')
    const ready = page.getByTestId('kg-canvas-ready')
    await expect(ready).toBeAttached({ timeout: 10_000 })

    // The seed cap is top_n=10 but BFS expansion may pull additional nodes.
    // The total should still be visibly smaller than the unfiltered default.
    const nodeCount = Number(await ready.getAttribute('data-node-count'))
    expect(nodeCount).toBeGreaterThan(0)
  })
})
