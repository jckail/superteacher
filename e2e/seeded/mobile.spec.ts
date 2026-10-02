import { test, expect, settled } from '../support/fixtures';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

const noHorizontalScroll = async (page: import('@playwright/test').Page) => {
  const overflow = await page.evaluate(() => {
    const el = document.documentElement;
    return { sw: el.scrollWidth, cw: el.clientWidth };
  });
  expect(overflow.sw, `page scrolls horizontally (${overflow.sw} > ${overflow.cw})`).toBeLessThanOrEqual(overflow.cw + 1);
};

test.describe('mobile 390px smoke: every page renders without console errors or page-level overflow', () => {
  const pages: [string, string, RegExp | string][] = [
    ['today', '/', 'Grade distribution'],
    ['roster', '/roster', 'Roster'],
    ['gradebook', '/gradebook', 'Gradebook'],
    ['attendance', '/attendance', 'Attendance'],
    ['reports', '/reports', 'Reports'],
    ['404', '/missing', 'Page not found'],
  ];
  for (const [name, url, text] of pages) {
    test(name, async ({ page }) => {
      await page.goto(url);
      await expect(page.getByRole('heading', { name: text }).first()).toBeVisible();
      await settled(page);
      await noHorizontalScroll(page);
    });
  }

  test('student page', async ({ page, api }) => {
    const [s] = await api.students();
    await page.goto(`/students/${s.id}`);
    await expect(page.getByRole('heading', { level: 1 })).toContainText(s.name);
    await settled(page);
    await noHorizontalScroll(page);
  });

  test('navigation, chat and a modal are usable', async ({ page }) => {
    await page.goto('/roster');
    await expect(page.locator('tbody tr').first()).toBeVisible();
    await page.getByRole('button', { name: '+ Student' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(391);
    await page.keyboard.press('Escape');

    await page.getByRole('button', { name: 'Ask AI' }).click();
    const chat = page.getByRole('complementary', { name: 'Super Teacher assistant' });
    await expect(chat).toBeVisible();
    await expect(chat.getByLabel('Message')).toBeVisible();
    const cb = await chat.boundingBox();
    expect(cb!.x + cb!.width).toBeLessThanOrEqual(391);
  });
});

test('theme toggle switches and persists across reload', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible(); // reachable on phones too
  const html = page.locator('html');
  const before = await html.getAttribute('data-theme');
  await page.getByRole('button', { name: /Switch to (light|dark) theme/ }).click();
  const after = await html.getAttribute('data-theme');
  expect(after).not.toBe(before);
  await page.reload();
  await expect(html).toHaveAttribute('data-theme', after!);
});
