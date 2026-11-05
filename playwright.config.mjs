import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/playwright',
  timeout: 30_000,
  use: {
    baseURL: process.env.GEOSITION_BASE_URL || 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
  },
});
