import { test, expect, uid } from '../support/fixtures';

test('student page: rule-based insight, notes persist, remove asks for confirmation', async ({ page, api }) => {
  const name = uid('Eve ');
  const c = await api.classroom({ studentNames: [name] });
  const a = await api.assessment(c.sectionId, 'Test 1', 100, 'test');
  const aid = a.assessments[0].id;
  await page.request.put(`/api/assessments/${aid}/scores`, { data: { scores: [{ student_id: c.students[0].id, points: 41 }] }, headers: { 'X-Requested-With': 'superteacher' } });

  await page.goto('/roster');
  await page.getByRole('link', { name, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/students/${c.students[0].id}$`));
  await expect(page.getByRole('heading', { level: 1 })).toContainText(name);

  // With AI unavailable, the card identifies its recorded-data basis and provides a useful headline.
  const insight = page.locator('section.insight');
  await expect(insight.getByText('Rule-based')).toBeVisible();
  await expect(insight.getByText('This summary uses recorded grades and attendance. AI-written suggestions are unavailable.', { exact: true })).toBeVisible();
  await expect(insight.locator('strong')).not.toBeEmpty();

  // notes
  const note = `Needs seat near the front ${uid()}`;
  await page.getByLabel('New note').fill(note);
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Note added')).toBeVisible();
  await expect(page.locator('.note', { hasText: note })).toBeVisible();
  await page.reload();
  await expect(page.locator('.note', { hasText: note })).toBeVisible();

  // removal needs an explicit confirmation; cancel keeps the student
  await page.getByRole('button', { name: 'Remove student' }).click();
  const dialog = page.getByRole('alertdialog', { name: `Remove ${name}?` });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Cancel' })).toBeFocused();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('heading', { level: 1 })).toContainText(name);

  await page.getByRole('button', { name: 'Remove student' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Remove student' }).click();
  await expect(page).toHaveURL(/\/roster/);
  await expect(page.getByText('Student removed')).toBeVisible();
  expect((await page.request.get(`/api/students/${c.students[0].id}`)).status()).toBe(404);
});

test('a student that does not exist shows a friendly not-found state', async ({ page, allowConsole }) => {
  allowConsole(/status of 404/);
  await page.goto('/students/does-not-exist');
  await expect(page.getByText('Student not found')).toBeVisible();
  await page.getByRole('link', { name: 'Back to roster' }).click();
  await expect(page).toHaveURL(/\/roster/);
});
