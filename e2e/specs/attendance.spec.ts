import { test, expect, uid, useClassroom, utcDaysAgo, utcToday } from '../support/fixtures';

test('attendance: mark statuses, bulk-present, persists after reload and across dates', async ({ page, api }) => {
  const names = ['Aa', 'Bb', 'Cc', 'Dd'].map((p) => `${p} ${uid()}`);
  const c = await api.classroom({ studentNames: names });
  await useClassroom(page, c);
  await page.goto('/attendance');
  const grp = (n: string) => page.getByRole('group', { name: `Attendance for ${n}` });
  const pressed = (n: string, s: string) => grp(n).getByRole('button', { name: s, exact: true });

  await expect(page.getByText('4 not yet marked')).toBeVisible();
  await pressed(names[0], 'Absent').click();
  await expect(pressed(names[0], 'Absent')).toHaveAttribute('aria-pressed', 'true');
  await pressed(names[1], 'Tardy').click();
  await pressed(names[2], 'Excused').click();
  await expect(page.getByText('1 not yet marked')).toBeVisible();

  await page.getByRole('button', { name: 'Mark 1 unmarked present' }).click();
  await expect(page.getByText('All marked ✓')).toBeVisible();
  await expect(pressed(names[3], 'Present')).toHaveAttribute('aria-pressed', 'true');
  // explicit marks were not overwritten by the bulk action
  await expect(pressed(names[0], 'Absent')).toHaveAttribute('aria-pressed', 'true');

  await page.reload();
  await expect(page.getByText('All marked ✓')).toBeVisible();
  await expect(pressed(names[0], 'Absent')).toHaveAttribute('aria-pressed', 'true');
  await expect(pressed(names[1], 'Tardy')).toHaveAttribute('aria-pressed', 'true');
  await expect(pressed(names[2], 'Excused')).toHaveAttribute('aria-pressed', 'true');
  await expect(pressed(names[3], 'Present')).toHaveAttribute('aria-pressed', 'true');

  // another day is an independent sheet
  await page.getByLabel('Date').fill(utcDaysAgo(1));
  await expect(page.getByText('4 not yet marked')).toBeVisible();
  await pressed(names[3], 'Absent').click();
  await expect(pressed(names[3], 'Absent')).toHaveAttribute('aria-pressed', 'true');

  await page.getByLabel('Date').fill(utcToday());
  await expect(page.getByText('All marked ✓')).toBeVisible();
  await expect(pressed(names[3], 'Present')).toHaveAttribute('aria-pressed', 'true');

  const yesterday = await api.attendance(c.sectionId, utcDaysAgo(1));
  expect(yesterday.rows.filter((r: any) => r.status).map((r: any) => r.status)).toEqual(['absent']);
});

test('attendance for a section without students points to the roster', async ({ page, api }) => {
  const c = await api.classroom();
  await useClassroom(page, c);
  await page.goto('/attendance');
  await expect(page.getByText('No students in this section')).toBeVisible();
  await page.getByRole('link', { name: 'Add students' }).click();
  await expect(page).toHaveURL(/\/roster/);
});
