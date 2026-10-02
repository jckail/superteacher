import { test, expect } from '../support/fixtures';

test('modal: focus is trapped in both directions and Esc closes', async ({ page, api }) => {
  await api.classroom();
  await page.goto('/roster');
  const opener = page.getByRole('button', { name: '+ Student' });
  await opener.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Add student' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Name')).toBeFocused();

  // Tab many times: focus never leaves the dialog, in either direction
  for (let i = 0; i < 9; i++) {
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'))).toBe(true);
  }
  for (let i = 0; i < 9; i++) {
    await page.keyboard.press('Shift+Tab');
    expect(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]'))).toBe(true);
  }

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
});

// Known app bug (FINDINGS.md #1): Modal captures the opener in an effect, after a child's autoFocus already moved focus.
// test.fail() keeps the suite green today and turns red ("unexpectedly passed") the moment the bug is fixed.
test.fail('modal: focus returns to the opener after Esc [FINDINGS #1]', async ({ page, api }) => {
  await api.classroom();
  await page.goto('/roster');
  const opener = page.getByRole('button', { name: '+ Student' });
  await opener.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog', { name: 'Add student' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(opener).toBeFocused({ timeout: 2000 });
});

test.fail('confirm dialog is an alertdialog and restores focus on Esc [FINDINGS #1]', async ({ page, api }) => {
  const c = await api.classroom({ studentNames: ['Focus Tester'] });
  await page.goto(`/students/${c.students[0].id}`);
  const opener = page.getByRole('button', { name: 'Remove student' });
  await opener.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alertdialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('alertdialog')).toBeHidden();
  await expect(opener).toBeFocused();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Focus Tester');
});

test('skip link moves focus to main; route changes move focus to main', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('main#main')).toBeFocused();
  await page.getByRole('link', { name: 'Roster' }).click();
  await expect(page.locator('main#main')).toBeFocused();
  await expect(page).toHaveTitle('Roster · Super Teacher');
});
