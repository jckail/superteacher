import { test, expect, useClassroom } from '../support/fixtures';
import type { Page, Route } from '@playwright/test';
import type { Gradebook } from '../../web/src/types';
const section = { id: 'small-group-section', course_id: 'small-group-course', name: 'Group practice' };
const data: Gradebook = { as_of: '2026-10-02', section, assessments: [
  { id: 'due', section_id: section.id, title: 'Shared exercise', kind: 'homework', max_points: 10, due_date: '2026-10-02' },
  { id: 'quiz', section_id: section.id, title: 'Quiz', kind: 'quiz', max_points: 10, due_date: '2026-10-02' },
  { id: 'future', section_id: section.id, title: 'Future exercise', kind: 'homework', max_points: 10, due_date: '2026-10-03' },
], rows: [
  { student_id: 'ada', name: 'Ada', average: 0, letter: 'F', points: { due: null, quiz: 0, future: null } },
  { student_id: 'ben', name: 'Ben', average: 40, letter: 'F', points: { due: 0, quiz: 9, future: null } },
  { student_id: 'cara', name: 'Cara', average: null, letter: null, points: { due: null, quiz: null, future: null } },
] };
async function arrange(page: Page, current: () => typeof data = () => data) {
  await useClassroom(page, { courseId: section.course_id, sectionId: section.id });
  await page.route('**/api/courses', route => route.fulfill({ json: [{ id: section.course_id, name: 'Math', sections: [section] }] }));
  await page.route('**/api/calendar', route => route.fulfill({ json: { today: data.as_of, timezone: 'UTC' } }));
  await page.route(`**/api/sections/${section.id}/gradebook`, route => route.fulfill({ json: current() }));
  await page.goto('/gradebook');
  const builder = page.getByRole('region', { name: 'Small-group builder' });
  await expect(builder.getByRole('checkbox', { name: 'Include group 1 in suggested plan' })).toBeVisible();
  return builder;
}
for (const width of [1280, 390]) test(`small groups review due evidence and teacher-selected slots at ${width}px without writes`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  const writes: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET') writes.push(`${request.method()} ${new URL(request.url()).pathname}`); });
  const builder = await arrange(page);
  const group = builder.getByRole('group', { name: 'Suggested group 1' });
  await expect(group).toContainText('Ada · unscored'); await expect(group).toContainText('Cara · unscored'); await expect(group).not.toContainText('Ben');
  await expect(builder.getByLabel('Due assignment')).not.toContainText('Future exercise');
  await group.getByText('Recorded evidence for group 1', { exact: true }).click();
  await expect(group).toContainText('Shared exercise · due 2026-10-02 · unscored');
  await builder.getByLabel('Maximum students per group').fill('1');
  await builder.getByRole('checkbox', { name: 'Include group 1 in suggested plan' }).check();
  await builder.getByRole('checkbox', { name: 'Include group 2 in suggested plan' }).check();
  await builder.getByLabel('Available start time (school time)').fill('09:00');
  await builder.getByRole('button', { name: 'Suggest reteach slots', exact: true }).click();
  const plan = builder.getByRole('region', { name: 'Suggested reteach plan' });
  await expect(plan).toContainText('09:00–09:15 · Ada'); await expect(plan).toContainText('09:15–09:30 · Cara');
  const geometry = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(geometry.scroll).toBeLessThanOrEqual(geometry.width + 1);
  await builder.getByLabel('Group by').selectOption('weak');
  await expect(plan).toHaveCount(0);
  const weak = builder.getByRole('group', { name: 'Suggested group 1' });
  await expect(weak).toContainText('Ada · 0%'); await expect(weak).not.toContainText('Cara'); await expect(weak).not.toContainText('Ben');
  await expect(builder).toContainText('1 student lacks enough score evidence');
  expect(writes).toEqual([]);
});
test('actual optimistic score save hides grouping actions and cannot restore the reviewed plan', async ({ page }) => {
  let current = data;
  const builder = await arrange(page, () => current);
  await builder.getByRole('checkbox', { name: 'Include group 1 in suggested plan' }).check();
  await builder.getByLabel('Available start time (school time)').fill('09:00');
  await builder.getByRole('button', { name: 'Suggest reteach slots', exact: true }).click();
  await expect(builder.getByRole('region', { name: 'Suggested reteach plan' })).toBeVisible();
  let finish!: () => void;
  const pending = new Promise<void>(resolve => { finish = resolve; });
  let intercepted = false;
  await page.route('**/api/assessments/quiz/scores', async route => {
    expect(route.request().method()).toBe('PUT');
    expect(route.request().postDataJSON()).toEqual({ scores: [{ student_id: 'ben', points: 5 }] });
    intercepted = true;
    await pending;
    current = { ...data, rows: data.rows.map(row => row.student_id === 'ben' ? { ...row, points: { ...row.points, quiz: 5 }, average: 200 / 9, letter: 'F' } : row) };
    await route.fulfill({ json: current });
  });
  const cell = page.getByRole('textbox', { name: 'Ben, Quiz', exact: true });
  await cell.fill('5'); await cell.press('Tab');
  await expect.poll(() => intercepted).toBe(true);
  await expect(builder.getByRole('checkbox')).toHaveCount(0);
  await expect(builder.getByRole('region', { name: 'Suggested reteach plan' })).toHaveCount(0);
  finish();
  await expect(cell).toHaveValue('5');
  await expect(builder.getByRole('checkbox', { name: 'Include group 1 in suggested plan' })).not.toBeChecked();
  await expect(builder.getByRole('region', { name: 'Suggested reteach plan' })).toHaveCount(0);
});

for (const label of ['Available start time (school time)', 'Reteach date']) test(`unchanged calendar poll restores native ${label} focus without stealing outside focus at 390px`, async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  // Advance the actual 60-second query interval; real timers continue for query notifications.
  await page.clock.install({ time: new Date('2026-10-02T12:00:00Z') });
  const writes: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET') writes.push(`${request.method()} ${new URL(request.url()).pathname}`); });
  const builder = await arrange(page);
  await builder.getByRole('checkbox', { name: 'Include group 1 in suggested plan' }).check();
  await builder.getByLabel('Available start time (school time)').fill('09:00');
  await builder.getByRole('button', { name: 'Suggest reteach slots', exact: true }).click();
  const native = builder.getByLabel(label, { exact: true });
  const outside = page.getByRole('textbox', { name: 'Ben, Quiz', exact: true });
  for (const moveOutside of [false, true]) {
    let finish!: () => void;
    const pending = new Promise<void>(resolve => { finish = resolve; });
    let intercepted = false;
    const hold = async (route: Route) => {
      expect(route.request().method()).toBe('GET');
      intercepted = true;
      await pending;
      await route.fulfill({ json: { today: data.as_of, timezone: 'UTC' } });
    };
    await page.route('**/api/calendar', hold);
    try {
      await native.focus();
      await expect(native).toBeFocused();
      await page.clock.fastForward(60_001);
      await expect.poll(() => intercepted).toBe(true);
      await expect(builder.getByRole('checkbox')).toHaveCount(0);
      await expect(builder.getByRole('region', { name: 'Suggested reteach plan' })).toHaveCount(0);
      if (moveOutside) { await outside.focus(); await expect(outside).toBeFocused(); }
      finish();
      await expect(builder.getByRole('checkbox', { name: 'Include group 1 in suggested plan' })).toBeChecked();
      await expect(builder.getByRole('region', { name: 'Suggested reteach plan' })).toContainText('09:00–09:15 · Ada, Cara');
      await expect(builder.getByLabel('Available start time (school time)')).toHaveValue('09:00');
      await expect(builder.getByLabel('Reteach date')).toHaveValue(data.as_of);
      await expect(moveOutside ? outside : native).toBeFocused();
    } finally {
      finish();
      await page.unroute('**/api/calendar', hold);
    }
  }
  expect(writes).toEqual([]);
});
