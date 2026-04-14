import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration — runs tests against BOTH database backends
 * in a single test session.
 *
 * Two Playwright projects (duckdb, sqlite) each start their own
 * backend + frontend server pair on different ports. All screenshots
 * and logs land in e2e-screenshots/ with engine-prefixed slugs.
 *
 * Usage:
 *   npx playwright test                    # both engines
 *   npx playwright test --project=sqlite   # just sqlite
 *   npx playwright test --project=duckdb   # just duckdb
 *
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
  ],
  outputDir: 'e2e-screenshots',
  timeout: 90000,
  expect: { timeout: 10000 },
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  globalSetup: './e2e/global-setup.ts',

  projects: [
    {
      name: 'sqlite',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:5274',
      },
    },
    {
      name: 'duckdb',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://localhost:5275',
      },
    },
  ],

  webServer: [
    {
      command:
        'concurrently --kill-others --names "be,fe" ' +
        '"BACKEND_PORT=8101 uv run python -m claude_code_sessions.main --backend sqlite" ' +
        '"VITE_BACKEND_URL=http://localhost:8101 npx vite --port 5274"',
      url: 'http://localhost:8101/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      command:
        'concurrently --kill-others --names "be,fe" ' +
        '"BACKEND_PORT=8102 uv run python -m claude_code_sessions.main --backend duckdb" ' +
        '"VITE_BACKEND_URL=http://localhost:8102 npx vite --port 5275"',
      url: 'http://localhost:8102/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],
})
