import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 30_000,
  reporter: [['list']], outputDir: 'test-results',
  use: { baseURL: process.env.ASM_BROWSER_BASE_URL ?? 'http://127.0.0.1:8080', trace: 'off', video: 'off', screenshot: 'off' },
  projects: [
    { name: 'chromium-desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'chromium-narrow', grep: /@narrow/, use: { ...devices['Pixel 5'] } },
  ],
});
