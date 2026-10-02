import { test, expect, type Page } from '@playwright/test';
import { readdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ACCOUNTS_PORT } from '../playwright.config';

const OUTBOX = join(tmpdir(), `st-e2e-outbox-${ACCOUNTS_PORT}`);
const EMAIL = `teacher-${Date.now().toString(36)}@example.com`;

/** The sign-in link from the newest message addressed to `to` (the `file` mailer writes one JSON file per email). */
async function latestLink(to: string, notBefore = 0): Promise<string> {
  let link = '';
  await expect
    .poll(
      () => {
        try {
          const files = readdirSync(OUTBOX).filter((f) => f.endsWith('.json'));
          const msgs = files.map((f) => JSON.parse(readFileSync(join(OUTBOX, f), 'utf8'))).filter((m) => m.to === to);
          if (msgs.length <= notBefore) return '';
          link = /(https?:\/\/\S+\/auth\/verify#token=[\w-]+)/.exec(msgs[msgs.length - 1].text)?.[1] ?? '';
        } catch {
          return '';
        }
        return link;
      },
      { timeout: 10_000 },
    )
    .not.toBe('');
  return link;
}

async function requestLink(page: Page, email: string) {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByText(/synthetic data only/i).first()).toBeVisible();
  await page.getByLabel('Email address').fill(email);
  await page.getByRole('button', { name: /email me a sign-in link/i }).click();
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();
  await expect(page.getByRole('status')).toContainText(email);
}

test.describe.configure({ mode: 'serial' });

test('passwordless sign-in, starter classroom, single-use link, export, sign out, delete', async ({ page, browser }) => {
  // 1. request a link: same "check your email" state regardless of anything about the address
  await requestLink(page, EMAIL);
  const link = await latestLink(EMAIL);
  expect(link).toContain('/auth/verify#token='); // fragment, never a query string
  expect(link).not.toContain('?');

  // 2. a mail scanner GET-ing the page (no fragment sent to servers) must not burn the token
  const scanned = await page.request.get(link.split('#')[0]);
  expect(scanned.ok()).toBeTruthy();

  // 3. opening the link signs in; the token never stays in the address bar
  await page.goto(link);
  const nav = page.getByRole('navigation', { name: 'Main' });
  await expect(nav).toBeVisible();
  expect(page.url()).not.toContain('token');
  await expect(page.getByRole('note')).toContainText('synthetic data only');
  await expect(page.getByRole('button', { name: new RegExp(EMAIL, 'i') })).toBeVisible();

  // 4. the new account got a small synthetic starter classroom
  await page.getByRole('link', { name: /Roster/ }).click();
  await expect(page.getByRole('row').nth(6)).toBeVisible();
  const starterRows = await page.getByRole('row').count();
  expect(starterRows).toBeGreaterThan(6);

  // 5. the same link cannot be replayed (separate browser context = another person holding the email)
  const other = await browser.newContext({ baseURL: page.url().split('/').slice(0, 3).join('/') });
  const p2 = await other.newPage();
  await p2.goto(link);
  await expect(p2.getByRole('heading', { name: /couldn.t sign you in/i })).toBeVisible();
  await expect(p2.getByRole('link', { name: /request a new link/i })).toHaveAttribute('href', '/');
  await other.close();

  // 6. banner dismissal lasts for the session
  await page.getByRole('link', { name: /Today/ }).click();
  await page.getByRole('button', { name: /dismiss demo notice/i }).click();
  await expect(page.getByRole('note')).toHaveCount(0);

  // 7. export downloads JSON containing the starter data
  await page.getByRole('button', { name: new RegExp(EMAIL, 'i') }).click();
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Export my data' }).click()]);
  expect(download.suggestedFilename()).toBe('super-teacher-export.json');
  const doc = JSON.parse(readFileSync((await download.path())!, 'utf8'));
  expect(doc.account.email).toBe(EMAIL);
  expect(doc.courses.map((c: { name: string }) => c.name)).toEqual(['Algebra I', 'Biology']);

  // 8. chat history from this session is wiped on sign out (privacy)
  await page.evaluate(() => sessionStorage.setItem('st-chat', JSON.stringify([{ role: 'user', text: 'secret question' }])));
  await page.getByRole('button', { name: new RegExp(EMAIL, 'i') }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('st-chat'))).toBeNull();
  expect((await page.request.get('/api/overview')).status()).toBe(401);

  // 9. sign in again, then delete the account (typed confirmation required)
  await requestLink(page, EMAIL);
  await page.goto(await latestLink(EMAIL, 1));
  await expect(nav).toBeVisible();
  await page.getByRole('button', { name: new RegExp(EMAIL, 'i') }).click();
  await page.getByRole('button', { name: /delete account/i }).click();
  const dialog = page.getByRole('alertdialog');
  const confirm = dialog.getByRole('button', { name: 'Delete everything' });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/type .* to confirm/i).fill(EMAIL);
  await confirm.click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  expect((await page.request.get('/api/overview')).status()).toBe(401);
});
