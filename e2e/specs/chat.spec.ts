import { test, expect } from '../support/fixtures';

test('chat panel without an API key explains itself and stays usable', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Ask AI' }).click();
  const chat = page.getByRole('complementary', { name: 'Super Teacher assistant' });
  await expect(chat).toBeVisible();
  await expect(chat.getByRole('textbox', { name: 'Message' })).toBeFocused();

  await chat.getByRole('textbox', { name: 'Message' }).fill('Who needs my attention?');
  await chat.getByRole('button', { name: 'Send' }).click();
  await expect(chat.getByText(/AI is not configured for this classroom yet/)).toBeVisible();
  await expect(chat.getByText('Your grades, attendance and reports are available.', { exact: false })).toBeVisible();
  await expect(chat.getByRole('button', { name: 'Send' })).toBeDisabled(); // empty input, not stuck busy
  await expect(chat.getByRole('textbox', { name: 'Message' })).toBeEnabled();

  // usable again: a second question gets the same notice (2 in the log)
  await chat.getByRole('textbox', { name: 'Message' }).fill('And attendance?');
  await chat.getByRole('button', { name: 'Send' }).click();
  await expect(chat.getByText(/AI is not configured/)).toHaveCount(2);

  // the rest of the app still works with the panel open
  await page.getByRole('link', { name: 'Roster' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Roster' })).toBeVisible();
  await chat.getByRole('button', { name: 'New chat' }).click();
  await expect(chat.getByText(/AI is not configured/)).toHaveCount(0);
  await chat.getByRole('button', { name: 'Close assistant' }).click();
  await expect(chat).toBeHidden();
});
