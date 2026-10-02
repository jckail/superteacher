import { test, expect, uid } from '../support/fixtures';

test('create a course, then a section in it', async ({ page }) => {
  const course = uid('Chem ');
  await page.goto('/roster');
  await page.getByRole('button', { name: '+ Course' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add course or section' });
  await dialog.getByLabel('Course name').fill(course);
  await dialog.getByRole('button', { name: 'Create' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(`Added ${course}`)).toBeVisible();

  await page.getByRole('button', { name: '+ Course' }).click();
  await page.getByRole('dialog').getByLabel('Add to').selectOption({ label: `${course} (new section)` });
  await page.getByRole('dialog').getByLabel('Section name').fill('Period 6');
  await page.getByRole('dialog').getByRole('button', { name: 'Create' }).click();
  await expect(page.getByText('Added section Period 6')).toBeVisible();

  const courses = await page.request.get('/api/courses').then((r) => r.json());
  const made = courses.find((c: any) => c.name === course);
  expect(made.sections.map((s: any) => s.name).sort()).toEqual(['Period 1', 'Period 6']);
});

test('add a student and see them on the roster', async ({ page, api }) => {
  const c = await api.classroom();
  const name = uid('Ada ');
  await page.addInitScript((s) => localStorage.setItem('st-scope', JSON.stringify(s)), { courseId: c.courseId, sectionId: c.sectionId });
  await page.goto('/roster');
  await expect(page.getByText('No students yet')).toBeVisible();
  await page.getByRole('button', { name: '+ Student' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add student' });
  await expect(dialog.getByLabel('Name')).toBeFocused();
  await dialog.getByLabel('Name').fill(name);
  await dialog.getByLabel('Grade level').selectOption('7');
  await dialog.getByLabel('Section').selectOption({ value: c.sectionId });
  await dialog.getByRole('button', { name: 'Add student' }).click();
  await expect(page.getByText(`Added ${name}`)).toBeVisible();
  const row = page.getByRole('row', { name: new RegExp(name) });
  await expect(row).toBeVisible();
  await expect(row).toContainText('Grade 7');
});

test('CSV import adds good rows and explains every skipped row', async ({ page, api }) => {
  const c = await api.classroom();
  const good = [uid('Grace '), uid('Alan ')];
  await page.addInitScript((s) => localStorage.setItem('st-scope', JSON.stringify(s)), { courseId: c.courseId, sectionId: c.sectionId });
  await page.goto('/roster');
  await page.getByRole('button', { name: 'Import CSV' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Import students from CSV' });
  await dialog.getByLabel('Section').selectOption({ value: c.sectionId });
  const csv = [`name,grade_level`, `${good[0]},10`, `,11`, `Bad Grade ${uid()},99`, `Not A Number ${uid()},abc`, `${good[1]},12`].join('\n');
  await dialog.getByLabel('CSV text').fill(csv);
  await dialog.getByRole('button', { name: 'Import' }).click();

  const status = dialog.getByRole('status');
  await expect(status).toContainText('2 added.');
  const skipped = status.getByRole('listitem');
  await expect(skipped).toHaveCount(3);
  for (const li of await skipped.all()) await expect(li).not.toBeEmpty();
  await expect(status).toContainText(/row 3/i);

  await dialog.getByRole('button', { name: 'Done' }).click();
  for (const n of good) await expect(page.getByRole('link', { name: n })).toBeVisible();
});

test('CSV import from a file upload', async ({ page, api }) => {
  const c = await api.classroom();
  const name = uid('Upload ');
  await page.addInitScript((s) => localStorage.setItem('st-scope', JSON.stringify(s)), { courseId: c.courseId, sectionId: c.sectionId });
  await page.goto('/roster');
  await page.getByRole('button', { name: 'Import CSV' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Section').selectOption({ value: c.sectionId });
  await dialog.getByLabel(/CSV file/).setInputFiles({ name: 'class.csv', mimeType: 'text/csv', buffer: Buffer.from(`name,grade_level\n${name},8\n`) });
  await expect(dialog.getByLabel('CSV text')).toHaveValue(/Upload/);
  await dialog.getByRole('button', { name: 'Import' }).click();
  await expect(dialog.getByRole('status')).toContainText('1 added.');
});
