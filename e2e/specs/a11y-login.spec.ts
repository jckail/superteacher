import { test, expect, setTheme } from '../support/fixtures';
import { auditA11y, VIEWPORTS } from '../support/axe';

test.describe('accessibility: login screen and empty states', () => {
  for (const [vpName, vp] of Object.entries(VIEWPORTS)) {
    for (const theme of ['light', 'dark'] as const) {
      test.describe(`${vpName} / ${theme}`, () => {
        test.use({ viewport: vp });

        test('login', async ({ browser, baseURL, allowConsole }, info) => {
          allowConsole(/status of 401/);
          const ctx = await browser.newContext({ viewport: vp, baseURL, storageState: { cookies: [], origins: [] } });
          const page = await ctx.newPage();
          await setTheme(page, theme);
          await page.goto('/');
          await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
          await auditA11y(page, `login|${vpName}|${theme}`, info);
          // Stub the rejection so the suite never burns the server's real login rate-limit budget.
          await page.route('**/api/auth/login', (r) => r.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"Invalid passcode"}' }));
          await page.getByLabel('Passcode').fill('wrong');
          await page.getByRole('button', { name: 'Sign in' }).click();
          await expect(page.getByRole('alert')).toBeVisible();
          await auditA11y(page, `login-error|${vpName}|${theme}`, info);
          await ctx.close();
        });

        test('empty classroom pages', async ({ page, api }, info) => {
          await setTheme(page, theme);
          const c = await api.classroom();
          await page.addInitScript((s) => localStorage.setItem('st-scope', JSON.stringify(s)), { courseId: c.courseId, sectionId: c.sectionId });
          for (const [path, text] of [['/roster', 'No students yet'], ['/gradebook', 'No students in this section'], ['/attendance', 'No students in this section'], ['/reports', 'No students in this section yet']] as const) {
            await page.goto(path);
            await expect(page.getByText(text).first()).toBeVisible();
            await auditA11y(page, `empty:${path}|${vpName}|${theme}`, info);
          }
        });
      });
    }
  }
});
