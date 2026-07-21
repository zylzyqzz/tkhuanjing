import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['html', {open:'never'}], ['github']] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173/tk-admin/',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{name:'chromium', use:{...devices['Desktop Chrome'], channel:'chromium'}}],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173/tk-admin/',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
