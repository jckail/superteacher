import { test, expect } from '../support/fixtures';
import { PASSCODE } from '../playwright.config';

test.describe('authentication', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('wrong passcode is rejected, then the right one signs in', async ({ page, allowConsole }) => {
    allowConsole(/status of 401/); // the deliberate wrong passcode
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeDisabled();

    await page.getByLabel('Passcode').fill('definitely-wrong');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toHaveText('Incorrect passcode.');
    await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0);

    await page.getByLabel('Passcode').fill(PASSCODE);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('session survives a reload, and logout ends it', async ({ page }) => {
    await page.goto('/');
    await page.getByLabel('Passcode').fill(PASSCODE);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Sign in' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

    // the cookie is really gone: a reload stays on the login screen and the API is closed
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    const res = await page.request.get('/api/overview');
    expect(res.status()).toBe(401);
  });

  test('an unauthenticated deep link shows login, then lands on the deep link', async ({ page }) => {
    await page.goto('/gradebook');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
    await page.getByLabel('Passcode').fill(PASSCODE);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/gradebook$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Gradebook' })).toBeVisible();
  });

  test('protected API refuses requests without a session', async ({ request }) => {
    expect((await request.get('/api/students')).status()).toBe(401);
    expect((await request.get('/api/health')).ok()).toBeTruthy();
  });
});

test('unknown route shows the 404 page with a way back', async ({ page }) => {
  await page.goto('/no/such/page');
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
  await expect(page).toHaveTitle(/Not found/);
  await page.getByRole('link', { name: 'Back to Today' }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toContainText(/Good (morning|afternoon|evening)/);
});
