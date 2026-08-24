import { defineConfig, devices } from '@playwright/test'

const port = process.env.E2E_PORT ?? '8766'
const runId = (process.env.E2E_RUN_ID ?? String(process.pid)).replace(/[^A-Za-z0-9_-]/g, '_')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `PYTHONPATH=../src uv run --project .. python -m data2doc2data.cli --config /tmp/data2doc2data-playwright-${runId}/config.json setup --port ${port} --no-browser`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
