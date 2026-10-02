import { test, expect } from '../support/fixtures';

const student = {
  id: 'conference-student', name: 'Conference Ada', grade_level: 9,
  section_id: 'conference-section', section: 'Period 1', course_id: 'conference-course', course: 'Math',
  average: 112.5, letter: 'A', gpa: 4, trend: 0, attendance_rate: 95.5, homework_rate: 100,
  missing: 1, risk: 'on_track', risk_reasons: [], as_of: '2026-10-02',
  attendance: [], absences: 1, tardies: 2,
  scores: [{ assessment_id: 'a', title: 'Due assignment', kind: 'homework', due_date: '2026-10-02', max_points: 10, points: null, pct: null }],
  notes: [{ id: 'n', body: 'Teacher-approved conference observation', created_at: '2026-10-01' }],
};

for (const width of [1280, 390]) test(`conference summary prints one page and contains only approved notes at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 844 });
  await page.route('**/api/calendar', route => route.fulfill({ json: { timezone: 'UTC', today: student.as_of } }));
  await page.route(`**/api/students/${student.id}`, route => route.fulfill({ json: student }));
  await page.goto(`/students/${student.id}/conference`);
  const sheet = page.getByRole('article', { name: `Conference summary for ${student.name}` });
  const print = page.getByRole('button', { name: 'Print conference sheet' });
  await expect(print).toBeEnabled();
  await expect(sheet).toContainText('112.5% (A)');
  await expect(sheet).toContainText('0 percentage points');
  await expect(sheet).not.toContainText(student.notes[0].body);
  await expect(page.getByRole('checkbox', { name: student.notes[0].body })).not.toBeChecked();
  const bounds = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(bounds.scroll).toBeLessThanOrEqual(bounds.width + 1);
  await page.getByRole('checkbox', { name: student.notes[0].body }).check();
  await expect(sheet).toContainText(student.notes[0].body);
  await expect(print).toBeEnabled();
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden();
  await expect(print).toBeHidden();
  const geometry = await sheet.evaluate(node => ({ height: node.clientHeight, scrollHeight: node.scrollHeight, width: node.clientWidth, scrollWidth: node.scrollWidth }));
  expect(geometry.scrollHeight).toBeLessThanOrEqual(geometry.height + 1);
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width + 1);
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
  // Chromium's PDF page dictionaries are uncompressed; exclude the /Pages tree.
  expect(pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)).toHaveLength(1);
  await info.attach(`conference-${width}.pdf`, { body: pdf, contentType: 'application/pdf' });
});

test('overlong approved note disables print and native print shows a warning without private data', async ({ page }) => {
  const long = { ...student, notes: [{ ...student.notes[0], body: 'Long private observation. '.repeat(700) }] };
  await page.route('**/api/calendar', route => route.fulfill({ json: { timezone: 'UTC', today: student.as_of } }));
  await page.route(`**/api/students/${student.id}`, route => route.fulfill({ json: long }));
  await page.goto(`/students/${student.id}/conference`);
  const print = page.getByRole('button', { name: 'Print conference sheet' });
  await expect(print).toBeEnabled();
  const note = page.getByRole('checkbox', { name: long.notes[0].body });
  await note.check();
  await expect(print).toBeDisabled();
  await expect(page.getByRole('status')).toContainText('exceeds one page');
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByRole('article')).toBeHidden();
  await expect(page.getByText('Refresh the summary and choose content that fits one page before printing.')).toBeVisible();
  await page.emulateMedia({ media: 'screen' });
  await note.uncheck();
  await expect(print).toBeEnabled();
});

test('roster conference entry opens the actual selected student', async ({ page, api }) => {
  const [s] = await api.students();
  await page.goto('/roster');
  // Search keeps the selected student discoverable despite server-side paging/risk sorting.
  await page.getByRole('searchbox', { name: 'Search students' }).fill(s.name);
  await page.getByRole('link', { name: `Conference sheet for ${s.name}`, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/students/${s.id}/conference$`));
  await expect(page.getByRole('article', { name: `Conference summary for ${s.name}` })).toBeVisible();
});
