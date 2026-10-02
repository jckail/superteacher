import { readFile } from 'node:fs/promises';
import { test, expect, uid, useClassroom } from '../support/fixtures';

test('reports: stats, CSV download neutralises formula injection, parent draft uses the template fallback', async ({ page, api }) => {
  const evil = '=HYPERLINK("http://evil.example/x","click")';
  const plain = uid('Pat ');
  const c = await api.classroom({ studentNames: [evil, plain] });
  const hw = await api.assessment(c.sectionId, '@SUM(1+1) Homework', 10);
  const aid = hw.assessments[0].id;
  await page.request.put(`/api/assessments/${aid}/scores`, {
    data: { scores: [{ student_id: c.students[0].id, points: 9 }, { student_id: c.students[1].id, points: 5 }] },
    headers: { 'X-Requested-With': 'superteacher' },
  });
  await useClassroom(page, c);
  await page.goto('/reports');
  await expect(page.getByRole('heading', { level: 1, name: 'Reports' })).toBeVisible();

  // stats
  const stat = (label: string) => page.locator('.stat', { hasText: label }).locator('.value');
  await expect(stat('Students')).toHaveText('2');
  await expect(stat('Class average')).toHaveText('70%');
  await expect(page.getByRole('img', { name: /Class average by assessment/ })).toBeVisible();
  await page.getByText('Show the numbers').click();
  await expect(page.getByRole('table').first()).toContainText('Homework');

  // CSV download
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: 'Download CSV' }).click()]);
  expect(download.suggestedFilename()).toMatch(/^gradebook-.*\.csv$/);
  const text = await readFile((await download.path())!, 'utf8');
  const lines = text.trim().split('\r\n');
  expect(lines[0]).toContain("'@SUM(1+1) Homework (10 pts)"); // header is neutralised too
  const evilLine = lines.find((l) => l.includes('HYPERLINK'))!;
  expect(evilLine.startsWith(`"'=HYPERLINK`)).toBe(true); // csv-quoted, leading apostrophe defuses the formula
  expect(lines.every((l) => !/^"?[=+\-@]/.test(l))).toBe(true); // no cell begins with a formula trigger
  const plainLine = lines.find((l) => l.startsWith(plain))!;
  expect(plainLine).toMatch(/,50(\.0)?,F,5$/);

  // parent update, no AI key -> template
  const composer = page.locator('.rep-composer');
  await expect(composer.getByRole('button', { name: 'Generate draft' })).toBeDisabled();
  await composer.getByLabel('Student').selectOption({ label: plain });
  await composer.getByLabel('Tone').selectOption('concerned');
  await composer.getByRole('button', { name: 'Generate draft' }).click();
  await expect(composer.getByText('Template draft')).toBeVisible();
  await expect(composer.getByLabel('Subject')).not.toHaveValue('');
  const body = await composer.getByLabel('Message').inputValue();
  expect(body).toContain(plain.split(' ')[0]);
  await composer.getByLabel('Message').fill(body + '\nEdited by teacher.');
  await expect(composer.getByRole('link', { name: 'Open in email' })).toHaveAttribute('href', /^mailto:\?subject=.*Edited%20by%20teacher/);
  await expect(composer.getByRole('button', { name: 'Regenerate' })).toBeVisible();
});
