/**
 * Playwright global setup — warm up the Vite dev server.
 *
 * Vite compiles the JS bundle lazily on first request. This setup visits
 * the frontend once to trigger compilation before test workers start.
 */
import { chromium } from '@playwright/test'

const FRONTEND_URLS = ['http://localhost:5274']

export default async function globalSetup(): Promise<void> {
  const browser = await chromium.launch()

  for (const url of FRONTEND_URLS) {
    const page = await browser.newPage()
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
      await page.waitForFunction(
        () => (document.getElementById('root')?.children.length ?? 0) > 0,
        { timeout: 30000 },
      ).catch(() => {
        console.warn(`Global setup: React failed to mount at ${url}`)
      })
    } finally {
      await page.close()
    }
  }

  await browser.close()
}
