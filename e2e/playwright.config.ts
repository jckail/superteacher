import { defineConfig, devices } from '@playwright/test';

export const PASSCODE = process.env.E2E_PASSWORD ?? 'e2e-passcode';
export const MAIN_PORT = Number(process.env.E2E_PORT ?? 18080); // empty DB, SEED_DEMO_DATA=false
export const SEEDED_PORT = Number(process.env.E2E_SEEDED_PORT ?? 18081); // deterministic demo classroom
export const ACCOUNTS_PORT = Number(process.env.E2E_ACCOUNTS_PORT ?? 18082); // AUTH_MODE=accounts, file mailer
export const MAIN_URL = `http://127.0.0.1:${MAIN_PORT}`;
export const SEEDED_URL = `http://127.0.0.1:${SEEDED_PORT}`;
export const ACCOUNTS_URL = `http://127.0.0.1:${ACCOUNTS_PORT}`;

const server = (port: number, seed: boolean, mode = 'passcode') => ({
  command: `node scripts/serve.mjs ${port} ${seed} ${mode}`,
  url: `http://127.0.0.1:${port}/api/health`,
  reuseExistingServer: false,
  timeout: 60_000,
  stdout: 'pipe' as const,
  stderr: 'pipe' as const,
});

export default defineConfig({
  testDir: '.',
  outputDir: 'test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list'], ['html', { open: 'never' }]],
  use: { trace: 'retain-on-failure', screenshot: 'only-on-failure', reducedMotion: 'reduce', locale: 'en-US', timezoneId: 'UTC' },
  webServer: [server(MAIN_PORT, false), server(SEEDED_PORT, true), server(ACCOUNTS_PORT, false, 'accounts')],
  projects: [
    { name: 'setup-main', testMatch: /support\/setup\.main\.ts/, use: { baseURL: MAIN_URL } },
    { name: 'setup-seeded', testMatch: /support\/setup\.seeded\.ts/, use: { baseURL: SEEDED_URL } },
    {
      name: 'workflows',
      testDir: './specs',
      dependencies: ['setup-main'],
      use: { ...devices['Desktop Chrome'], baseURL: MAIN_URL, storageState: '.auth/main.json' },
    },
    {
      name: 'seeded',
      testDir: './seeded',
      dependencies: ['setup-seeded', 'workflows'],
      use: { ...devices['Desktop Chrome'], baseURL: SEEDED_URL, storageState: '.auth/seeded.json' },
    },
    {
      // Passwordless accounts flow against a third server (AUTH_MODE=accounts, file mailer). No shared state with the others.
      name: 'accounts',
      testDir: './accounts',
      use: { ...devices['Desktop Chrome'], baseURL: ACCOUNTS_URL },
    },
  ],
});
