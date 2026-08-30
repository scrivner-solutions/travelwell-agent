import { defineConfig } from '@playwright/test'

/**
 * E2E + visual verification against the local dev stack. The viewport matches
 * the design prototype's phone frame (390x844) so screenshots line up with
 * the Claude Design canvas side by side.
 *
 * Requires the backend (uvicorn :8000, seeded) to be running; the vite dev
 * server is reused when present and started otherwise.
 */
export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/.results',
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 1,
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
  },
})
