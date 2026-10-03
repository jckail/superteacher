import { test, expect, setTheme } from '../support/fixtures';

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

test('dark-theme overlong note prints a readable warning without private data and restores screen colors', async ({ page }) => {
  await setTheme(page, 'light');
  const long = { ...student, notes: [{ ...student.notes[0], body: 'Long private observation. '.repeat(700) }] };
  await page.route('**/api/calendar', route => route.fulfill({ json: { timezone: 'UTC', today: student.as_of } }));
  await page.route(`**/api/students/${student.id}`, route => route.fulfill({ json: long }));
  await page.goto(`/students/${student.id}/conference`);
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('body')).toHaveCSS('color', 'rgb(239, 237, 250)');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(18, 16, 28)');
  const print = page.getByRole('button', { name: 'Print conference sheet' });
  await expect(print).toBeEnabled();
  const note = page.getByRole('checkbox', { name: long.notes[0].body });
  await note.check();
  await expect(print).toBeDisabled();
  await expect(page.getByRole('status').filter({ hasText: 'exceeds one page' })).toContainText('exceeds one page');
  await page.emulateMedia({ media: 'print' });
  await expect(page.getByRole('article')).toBeHidden();
  const warning = page.getByText('Refresh the summary and choose content that fits one page before printing.');
  await expect(warning).toBeVisible();
  await expect(warning).toHaveCSS('color', 'rgb(17, 17, 17)');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  const contrast = await warning.evaluate(node => {
    const luminance = (color: string) => {
      const channels = color.match(/\d+/g)!.slice(0, 3).map(value => {
        const channel = Number(value) / 255;
        return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
      });
      return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
    };
    const foreground = luminance(getComputedStyle(node).color);
    const background = luminance(getComputedStyle(document.body).backgroundColor);
    return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
  });
  expect(contrast).toBeGreaterThanOrEqual(7);
  expect(await page.locator('body').innerText()).not.toContain('Long private observation.');
  await page.emulateMedia({ media: 'screen' });
  await expect(warning).toBeHidden();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('body')).toHaveCSS('color', 'rgb(239, 237, 250)');
  await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(18, 16, 28)');
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

test('native conference print excludes an actual accounts dialog portal and leaves the screen dialog intact', async ({ page }, info) => {
  const email = 'conference-private-account@example.test';
  const writes: string[] = [];
  page.on('request', request => { if (request.method() !== 'GET') writes.push(`${request.method()} ${new URL(request.url()).pathname}`); });
  await page.route('**/api/auth/config', route => route.fulfill({ json: { auth_mode: 'accounts' } }));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { auth_required: true, auth_mode: 'accounts', email } }));
  await page.route('**/api/calendar', route => route.fulfill({ json: { timezone: 'UTC', today: student.as_of } }));
  await page.route(`**/api/students/${student.id}`, route => route.fulfill({ json: student }));
  await page.goto(`/students/${student.id}/conference`);
  await expect(page.getByRole('button', { name: 'Print conference sheet' })).toBeEnabled();
  await page.getByRole('button', { name: email }).click();
  await page.getByRole('button', { name: 'Delete account…' }).click();
  const dialog = page.getByRole('alertdialog', { name: 'Delete your account?' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(email);
  await expect(dialog.getByRole('button', { name: 'Delete account' })).toBeDisabled();
  await expect(page.locator('body > .scrim')).toBeVisible();
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('body > .scrim')).toBeHidden();
  await expect(page.locator('.conference-sheet')).toBeVisible();
  const printedText = await page.locator('body').innerText();
  expect(printedText).toContain(student.name);
  expect(printedText).not.toContain(email);
  expect(printedText).not.toContain('Delete your account?');
  expect(printedText).not.toContain('Delete account');
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
  expect(pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)).toHaveLength(1);
  await info.attach('conference-with-account-portal.pdf', { body: pdf, contentType: 'application/pdf' });
  await page.emulateMedia({ media: 'screen' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(email);
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(writes).toEqual([]);
});

for (const width of [1280, 390]) test(`conference chat preserves the selected student and stays out of print at ${width}px`, async ({ page }, info) => {
  const question = 'Private teacher question for this conference';
  const answer = 'Private synthetic assistant transcript';
  const messages: { student_id?: string; content: string }[] = [];
  await page.setViewportSize({ width, height: 844 });
  await page.route('**/api/calendar', route => route.fulfill({ json: { timezone: 'UTC', today: student.as_of } }));
  await page.route(`**/api/students/${student.id}`, route => route.fulfill({ json: student }));
  // Mock the real Chat transport without connecting it to a server/provider.
  await page.routeWebSocket('**/api/chat/ws', socket => {
    socket.onMessage(message => {
      messages.push(JSON.parse(message.toString()));
      socket.send(JSON.stringify({ type: 'delta', text: answer }));
      socket.send(JSON.stringify({ type: 'done' }));
    });
  });
  await page.goto(`/students/${student.id}/conference`);
  await expect(page.getByRole('button', { name: 'Print conference sheet' })).toBeEnabled();
  await page.getByRole('button', { name: 'Ask AI' }).click();
  const assistant = page.getByRole(width <= 1100 ? 'dialog' : 'complementary', { name: 'Super Teacher assistant' });
  await expect(assistant).toBeVisible();
  await expect(assistant).toContainText('Focused on this student');
  await assistant.getByRole('textbox', { name: 'Message' }).fill(question);
  await assistant.getByRole('button', { name: 'Send' }).click();
  await expect(assistant.getByText(answer, { exact: true })).toBeVisible();
  expect(messages).toEqual([{ content: question, student_id: student.id, tool_events: true }]);
  if (width <= 1100) await expect(page.locator('body > .chat')).toBeVisible();
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.chat')).toBeHidden();
  const printedText = await page.locator('body').innerText();
  expect(printedText).toContain(student.name);
  expect(printedText).not.toContain(question);
  expect(printedText).not.toContain(answer);
  expect(printedText).not.toContain('Ask Super Teacher');
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true, displayHeaderFooter: false });
  expect(pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)).toHaveLength(1);
  await info.attach(`conference-open-chat-${width}.pdf`, { body: pdf, contentType: 'application/pdf' });
  await page.emulateMedia({ media: 'screen' });
  await expect(assistant).toBeVisible();
  await expect(assistant.getByText(answer, { exact: true })).toBeVisible();
  await assistant.getByRole('button', { name: 'Close assistant' }).click();
  await expect(assistant).not.toBeVisible();
});
