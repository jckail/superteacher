import { test, expect, setTheme, settled } from '../support/fixtures';
import { auditA11y, VIEWPORTS } from '../support/axe';

const THEMES = ['light', 'dark'] as const;

test.describe('accessibility (axe-core, WCAG 2.x A/AA + best practices) - seeded data', () => {
  for (const [vpName, vp] of Object.entries(VIEWPORTS)) {
    for (const theme of THEMES) {
      test.describe(`${vpName} / ${theme}`, () => {
        test.use({ viewport: vp });
        test.beforeEach(async ({ page }) => setTheme(page, theme));

        const pages: [string, string, (p: import('@playwright/test').Page) => Promise<void>][] = [
          ['today', '/', (p) => expect(p.getByRole('heading', { name: /Grade distribution/ })).toBeVisible()],
          ['roster', '/roster', (p) => expect(p.locator('tbody tr').first()).toBeVisible()],
          ['gradebook', '/gradebook', (p) => expect(p.getByRole('textbox').first()).toBeVisible()],
          ['attendance', '/attendance', (p) => expect(p.getByRole('group').first()).toBeVisible()],
          ['reports', '/reports', (p) => expect(p.getByRole('img', { name: /Daily attendance/ })).toBeVisible()],
          ['not-found', '/nope', (p) => expect(p.getByRole('heading', { name: 'Page not found' })).toBeVisible()],
        ];
        for (const [name, url, ready] of pages) {
          test(name, async ({ page }, info) => {
            await page.goto(url);
            await ready(page);
            await settled(page);
            await auditA11y(page, `${name}|${vpName}|${theme}`, info);
          });
        }

        test('student detail', async ({ page, api }, info) => {
          const [s] = await api.students();
          await page.goto(`/students/${s.id}`);
          await expect(page.getByRole('heading', { level: 1 })).toContainText(s.name);
          await expect(page.locator('section.insight .chip')).toBeVisible();
          await settled(page);
          await auditA11y(page, `student|${vpName}|${theme}`, info);
        });

        test('open modals (add student, import, course, assignment, confirm)', async ({ page, api }, info) => {
          await page.goto('/roster');
          await expect(page.locator('tbody tr').first()).toBeVisible();
          for (const [btn, title] of [['+ Student', 'Add student'], ['Import CSV', 'Import students from CSV'], ['+ Course', 'Add course or section']] as const) {
            await page.getByRole('button', { name: btn, exact: true }).click();
            await expect(page.getByRole('dialog', { name: title })).toBeVisible();
            await auditA11y(page, `modal:${title}|${vpName}|${theme}`, info);
            await page.keyboard.press('Escape');
            await expect(page.getByRole('dialog')).toBeHidden();
          }
          await page.goto('/gradebook');
          await page.getByRole('button', { name: '+ Assignment' }).click();
          await expect(page.getByRole('dialog', { name: 'New assignment' })).toBeVisible();
          await auditA11y(page, `modal:New assignment|${vpName}|${theme}`, info);
          await page.keyboard.press('Escape');

          const [s] = await api.students();
          await page.goto(`/students/${s.id}`);
          await page.getByRole('button', { name: 'Remove student' }).click();
          await expect(page.getByRole('alertdialog')).toBeVisible();
          await auditA11y(page, `modal:Confirm remove|${vpName}|${theme}`, info);
        });

        test('open chat panel (empty and after a reply)', async ({ page }, info) => {
          await page.goto('/');
          await expect(page.getByRole('heading', { name: /Grade distribution/ })).toBeVisible();
          await page.getByRole('button', { name: 'Ask AI' }).click();
          const chat = page.getByRole(vpName === 'mobile' ? 'dialog' : 'complementary', { name: 'Super Teacher assistant' });
          await expect(chat).toBeVisible();
          if (vpName === 'mobile') await expect(chat).toHaveAttribute('aria-modal', 'true');
          await auditA11y(page, `chat-empty|${vpName}|${theme}`, info);
          await chat.getByLabel('Message').fill('hello');
          await chat.getByRole('button', { name: 'Send' }).click();
          await expect(chat.getByText(/not configured/)).toBeVisible();
          await auditA11y(page, `chat-reply|${vpName}|${theme}`, info);
        });
      });
    }
  }
});
