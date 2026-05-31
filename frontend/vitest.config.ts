import path from 'node:path'

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Mirror vite.config's `@` alias so component tests can load pages/components
  // that use `@/` value imports (not just type-only imports).
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/e2e/**',  // Playwright E2E tests - run with `npm run test:e2e`
    ],
    passWithNoTests: true,
  },
})
