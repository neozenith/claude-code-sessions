import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for E2E filter tests.
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './e2e',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI */
  workers: process.env.CI ? 1 : undefined,
  /* Reporter to use */
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
  ],
  /* Shared settings for all projects */
  use: {
    /* Base URL to use in actions like `await page.goto('/')` */
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5274',
    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',
    /* Screenshot settings */
    screenshot: 'only-on-failure',
  },
  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  /* Output folder for screenshots */
  outputDir: 'e2e-screenshots',
  /* Timeout for each test */
  timeout: 30000,
  /* Timeout for expect() assertions */
  expect: {
    timeout: 10000,
  },
  /* Run your local dev server before starting the tests */
  webServer: {
    command: 'npm run agentic-dev',
    url: 'http://localhost:5274',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
})
