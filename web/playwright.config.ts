import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'http://127.0.0.1:8766',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'PYTHONPATH=../src python -m data2doc2data.cli --config /tmp/data2doc2data-playwright/config-$PPID.json setup --port 8766 --no-browser',
    url: 'http://127.0.0.1:8766',
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
