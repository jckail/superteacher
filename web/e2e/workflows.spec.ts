import { expect, test as base, type Page } from '@playwright/test';
import axe from 'axe-core';
import { randomUUID } from 'node:crypto';

const passcode = 'superteacher-browser-tests';
const test = base.extend<{ browserErrors: void }>({
  browserErrors: [async ({ page }, use, testInfo) => {
    const errors: string[] = [];
    const consoleErrors: { text: string; url: string }[] = [];
    const injectedFailureUrls = new Set<string>();
    page.on('pageerror', (error) => errors.push(`Uncaught exception: ${error.message}`));
    page.on('response', (response) => {
      if (response.status() === 503 && response.headers()['x-superteacher-e2e-fault'] === 'true') injectedFailureUrls.add(response.url());
    });
    page.on('console', (message) => {
      if (message.type() !== 'error') return;
      // Chromium reports expected failed HTTP responses as console errors.
      // Initial auth checks and deliberately invalid/expired sessions yield 401.
      if (/^Failed to load resource: the server responded with a status of 401\b/.test(message.text())) return;
      consoleErrors.push({ text: message.text(), url: message.location().url });
    });
    await use();
    for (const message of consoleErrors) {
      // Only marked synthetic faults may yield an expected 503 resource message.
      if (/^Failed to load resource: the server responded with a status of 503\b/.test(message.text) && injectedFailureUrls.has(message.url)) continue;
      errors.push(`Console error: ${message.text} (${message.url})`);
    }
    if (errors.length) await testInfo.attach('browser-errors', { body: errors.join('\n'), contentType: 'text/plain' });
    expect(errors, 'Browser application errors').toEqual([]);
  }, { auto: true }],
});

async function login(page: Page) {
  await page.goto('/roster');
  await page.getByLabel('Passcode').fill(passcode);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Roster', exact: true })).toBeVisible();
}

async function accessibility(page: Page) {
  // Runtime evaluation works with the production CSP without enabling bypassCSP.
  await page.evaluate(axe.source);
  const violations = await page.evaluate(async () => {
    const checker = (window as unknown as { axe: typeof axe }).axe;
    const results = await checker.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } });
    return results.violations.map(({ id, impact, nodes }) => ({ id, impact, targets: nodes.map((node) => node.target) }));
  });
  expect(violations, 'WCAG A/AA accessibility violations').toEqual([]);
}

async function createCourse(page: Page, name: string) {
  await page.getByRole('button', { name: '+ Course', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Add course or section' });
  await dialog.getByLabel('Course name').fill(name);
  await dialog.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.getByLabel('Course', { exact: true }).selectOption({ label: name });
}

test('teacher onboarding, durable grades/attendance, offline reports and private-session cleanup', async ({ page, context }) => {
  const attempt = randomUUID();
  const course = `Browser Biology ${attempt}`;
  const student = `Ada Browser ${attempt}`;
  await page.goto('/roster');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Roster', exact: true })).toBeHidden();
  await accessibility(page);
  await page.getByLabel('Passcode').fill('wrong-passcode');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Incorrect passcode');
  await page.getByLabel('Passcode').fill(passcode);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Roster', exact: true })).toBeVisible();
  await createCourse(page, course);

  await page.getByRole('button', { name: '+ Course', exact: true }).click();
  const sectionDialog = page.getByRole('dialog', { name: 'Add course or section' });
  await sectionDialog.getByLabel('Add to').selectOption({ label: `${course} (new section)` });
  await sectionDialog.getByLabel('Section name').fill('Period 2');
  await sectionDialog.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(sectionDialog).toBeHidden();
  await page.getByLabel('Section', { exact: true }).selectOption({ label: 'Period 2' });
  const sectionId = await page.getByLabel('Section', { exact: true }).inputValue();

  await page.getByRole('button', { name: '+ Student', exact: true }).click();
  const studentDialog = page.getByRole('dialog', { name: 'Add student' });
  await studentDialog.getByLabel('Name', { exact: true }).fill(student);
  await studentDialog.getByLabel('Grade level').selectOption('10');
  // Failed attempts leave synthetic courses in this server; section labels repeat across courses.
  await studentDialog.getByRole('combobox', { name: 'Section', exact: true }).selectOption(sectionId);
  await studentDialog.getByRole('button', { name: 'Add student', exact: true }).click();
  await expect(studentDialog).toBeHidden();
  await expect(page.getByRole('link', { name: student, exact: true })).toBeVisible();
  await accessibility(page);

  await page.getByRole('link', { name: 'Gradebook', exact: true }).click();
  await page.getByRole('button', { name: '+ Assignment', exact: true }).click();
  const assignment = page.getByRole('dialog', { name: 'New assignment' });
  await assignment.getByLabel('Title', { exact: true }).fill('Browser quiz');
  await assignment.getByRole('combobox', { name: 'Type', exact: true }).selectOption('quiz');
  await assignment.getByLabel('Max points').fill('20');
  await assignment.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(assignment).toBeHidden();
  const score = page.getByRole('textbox', { name: `${student}, Browser quiz`, exact: true });
  await score.fill('17');
  const gradeSaved = page.waitForResponse((response) => response.url().includes('/scores') && response.request().method() === 'PUT' && response.ok());
  await score.press('Enter');
  await gradeSaved;
  await page.reload();
  await expect(score).toHaveValue('17');
  await expect(page.getByRole('row').filter({ has: page.getByRole('link', { name: student, exact: true }) })).toContainText('85%');
  await accessibility(page);

  await page.getByRole('link', { name: 'Attendance', exact: true }).click();
  const attendance = page.getByRole('group', { name: `Attendance for ${student}`, exact: true });
  const attendanceSaved = page.waitForResponse((response) => response.url().includes('/attendance') && response.request().method() === 'PUT' && response.ok());
  await attendance.getByRole('button', { name: 'Absent', exact: true }).click();
  await attendanceSaved;
  await page.reload();
  await expect(attendance.getByRole('button', { name: 'Absent', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await accessibility(page);

  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Assessment averages' })).toBeVisible();
  await page.getByRole('combobox', { name: 'Student', exact: true }).selectOption({ label: student });
  await page.getByRole('button', { name: 'Generate draft' }).click();
  await expect(page.getByText('Template draft', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Subject', { exact: true })).not.toHaveValue('');
  await expect(page.getByRole('textbox', { name: 'Message', exact: true })).toHaveValue(new RegExp(`Ada.*${course}`));
  await accessibility(page);

  await page.getByRole('button', { name: 'Ask AI', exact: true }).click();
  await page.locator('#assistant-panel').getByRole('textbox', { name: 'Message', exact: true }).fill('How can I help this class?');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('log', { name: 'Conversation' })).toContainText('AI is not configured');
  await page.getByRole('button', { name: 'Close assistant' }).click();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByText(student, { exact: true })).toBeHidden();
  expect(await page.evaluate(() => sessionStorage.getItem('st-chat'))).toBeNull();
  expect((await page.request.get('/api/students')).status()).toBe(401);

  await login(page);
  await expect(page.getByRole('link', { name: student, exact: true })).toBeVisible();
  await page.evaluate(() => sessionStorage.setItem('st-chat', JSON.stringify([{ role: 'user', text: 'Private conversation' }])));
  // Expire the real browser cookie, then trigger an uncached protected request.
  await context.clearCookies();
  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByText(student, { exact: true })).toBeHidden();
  expect(await page.evaluate(() => sessionStorage.getItem('st-chat'))).toBeNull();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
});

test('assignment, student profile and private notes can be corrected and persist after reload', async ({ page }) => {
  const attempt = randomUUID();
  const course = `Browser Corrections ${attempt}`;
  const student = `Grace Browser ${attempt}`;
  const renamed = `Grace Updated ${attempt}`;
  await login(page);
  await createCourse(page, course);
  const courseId = await page.getByLabel('Course', { exact: true }).inputValue();
  await page.getByLabel('Section', { exact: true }).selectOption({ label: 'Period 1' });
  const sectionId = await page.getByLabel('Section', { exact: true }).inputValue();
  await page.getByRole('button', { name: '+ Student', exact: true }).click();
  const studentDialog = page.getByRole('dialog', { name: 'Add student' });
  await studentDialog.getByRole('textbox', { name: 'Name', exact: true }).fill(student);
  // The dialog defaults to the first section globally; select this course's section explicitly.
  await studentDialog.getByRole('combobox', { name: 'Section', exact: true }).selectOption(sectionId);
  await studentDialog.getByRole('button', { name: 'Add student', exact: true }).click();
  await expect(studentDialog).toBeHidden();
  await page.getByRole('link', { name: 'Gradebook', exact: true }).click();
  await page.getByRole('button', { name: '+ Assignment', exact: true }).click();
  const assignment = page.getByRole('dialog', { name: 'New assignment' });
  await assignment.getByRole('textbox', { name: 'Title', exact: true }).fill('Original quiz');
  await assignment.getByRole('spinbutton', { name: 'Max points', exact: true }).fill('20');
  await assignment.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(assignment).toBeHidden();
  const originalScore = page.getByRole('textbox', { name: `${student}, Original quiz`, exact: true });
  const scoresRoute = '**/api/assessments/*/scores';
  await page.route(scoresRoute, (route) => route.fulfill({ status: 503, headers: { 'x-superteacher-e2e-fault': 'true' }, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic score failure' }) }));
  await originalScore.fill('11');
  await originalScore.press('Enter');
  await expect(page.getByRole('alert')).toContainText('Synthetic score failure');
  await expect(originalScore).toHaveValue('');
  await page.getByRole('button', { name: /Dismiss notification:.*Synthetic score failure/ }).click();
  await page.unroute(scoresRoute);
  await originalScore.fill('17');
  const saved = page.waitForResponse((response) => response.url().includes('/scores') && response.request().method() === 'PUT' && response.ok());
  await originalScore.press('Enter');
  await saved;
  // A rejected edit must restore an existing grade as well as a blank cell.
  await page.route(scoresRoute, (route) => route.fulfill({ status: 503, headers: { 'x-superteacher-e2e-fault': 'true' }, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic score failure' }) }));
  await originalScore.fill('11');
  await originalScore.press('Enter');
  await expect(page.getByRole('alert')).toContainText('Synthetic score failure');
  await expect(originalScore).toHaveValue('17');
  await page.getByRole('button', { name: /Dismiss notification:.*Synthetic score failure/ }).click();
  await page.unroute(scoresRoute);
  await page.reload();
  await expect(originalScore).toHaveValue('17');
  await page.getByRole('button', { name: 'Edit Original quiz', exact: true }).click();
  const editAssignment = page.getByRole('dialog', { name: 'Edit assignment' });
  await editAssignment.getByRole('textbox', { name: 'Title', exact: true }).fill('Corrected quiz');
  await editAssignment.getByRole('spinbutton', { name: 'Max points', exact: true }).fill('25');
  await expect(editAssignment.getByRole('status')).toContainText('raw score unchanged');
  await editAssignment.getByRole('button', { name: 'Save assignment', exact: true }).click();
  await expect(editAssignment).toBeHidden();
  await page.reload();
  await expect(page.getByRole('textbox', { name: `${student}, Corrected quiz`, exact: true })).toHaveValue('17');
  await expect(page.getByRole('row').filter({ has: page.getByRole('link', { name: student, exact: true }) })).toContainText('68%');
  await page.getByRole('link', { name: student, exact: true }).click();
  await page.getByRole('button', { name: 'Edit student', exact: true }).click();
  const profile = page.getByRole('dialog', { name: 'Edit student', exact: true });
  await profile.getByRole('textbox', { name: 'Name', exact: true }).fill(renamed);
  await profile.getByRole('spinbutton', { name: 'Grade level', exact: true }).fill('11');
  await profile.getByRole('button', { name: 'Save student', exact: true }).click();
  await expect(profile).toBeHidden();
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toContainText(renamed);
  await expect(page.getByText(`Grade 11 · ${course} · Period 1`, { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'New note', exact: true }).fill('Original private observation');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByRole('button', { name: 'Edit note: Original private observation', exact: true }).click();
  const note = page.getByRole('dialog', { name: 'Edit private note', exact: true });
  await note.getByRole('textbox', { name: 'Note', exact: true }).fill('Corrected private observation');
  await note.getByRole('button', { name: 'Save note', exact: true }).click();
  await expect(note).toBeHidden();
  await page.reload();
  await expect(page.getByText('Corrected private observation', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Delete note: Corrected private observation', exact: true }).click();
  const confirmation = page.getByRole('alertdialog', { name: 'Delete private note?', exact: true });
  await confirmation.getByRole('button', { name: 'Delete note', exact: true }).click();
  await expect(confirmation).toBeHidden();
  await expect(page.getByText('Corrected private observation', { exact: true })).toBeHidden();
  await page.reload();
  await expect(page.getByText('Corrected private observation', { exact: true })).toBeHidden();

  // Provision only the destination in this run's authenticated temporary backend.
  const targetResponse = await page.request.post('/api/sections', { headers: { 'X-Requested-With': 'superteacher' }, data: { course_id: courseId, name: 'Transfer destination' } });
  expect(targetResponse.ok()).toBe(true);
  const target = await targetResponse.json() as { id: string };
  await page.reload();
  await page.getByRole('button', { name: 'Edit student', exact: true }).click();
  await profile.getByRole('combobox', { name: 'Section', exact: true }).selectOption(target.id);
  await expect(profile.getByRole('status')).toContainText('preserves grade history');
  await profile.getByRole('button', { name: 'Save student', exact: true }).click();
  await expect(profile).toBeHidden();
  await page.reload();
  await expect(page.getByText(`Grade 11 · ${course} · Transfer destination`, { exact: true })).toBeVisible();
  const activeAverage = page.locator('.stat').filter({ has: page.getByText('Average', { exact: true }) }).locator('.value');
  await expect(activeAverage).toHaveText('—');
  const history = page.getByRole('region', { name: 'Grade history', exact: true });
  await expect(history.getByRole('row').filter({ hasText: 'Corrected quiz' })).toContainText('17/25 (68%)');
  await accessibility(page);
  await page.getByRole('button', { name: 'Edit student', exact: true }).click();
  await profile.getByRole('combobox', { name: 'Section', exact: true }).selectOption(sectionId);
  await profile.getByRole('button', { name: 'Save student', exact: true }).click();
  await expect(profile).toBeHidden();
  await page.reload();
  await expect(page.getByText(`Grade 11 · ${course} · Period 1`, { exact: true })).toBeVisible();
  await expect(activeAverage).toHaveText('68%');
  await expect(page.getByRole('region', { name: 'Grade history', exact: true }).getByText('Corrected quiz', { exact: true })).toBeHidden();
  await accessibility(page);
});

test('quoted CSV imports report partial failures, persist valid rows and recover from an HTTP read error', async ({ page }) => {
  const attempt = randomUUID();
  const course = `Browser Import ${attempt}`;
  const quotedName = `River "RJ", Browser ${attempt}`;
  const otherName = `Jamie Import ${attempt}`;
  await login(page);
  await createCourse(page, course);
  await page.getByLabel('Section', { exact: true }).selectOption({ label: 'Period 1' });
  const sectionId = await page.getByLabel('Section', { exact: true }).inputValue();
  await page.locator('.topbar').getByRole('button', { name: 'Import CSV', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Import students from CSV', exact: true });
  await dialog.getByRole('combobox', { name: 'Section', exact: true }).selectOption(sectionId);
  const quotedRow = `"${quotedName.replaceAll('"', '""')}",10`;
  const csv = ['name,grade_level', quotedRow, ',9', 'Outside Grade Range,13', quotedRow, `${otherName},11`].join('\n');
  await dialog.getByLabel('CSV file (columns: name, grade_level)', { exact: true }).setInputFiles({ name: 'synthetic-roster.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await expect(dialog.getByRole('textbox', { name: 'CSV text', exact: true })).toHaveValue(csv);
  await dialog.getByRole('button', { name: 'Import', exact: true }).click();
  const feedback = dialog.getByRole('status');
  await expect(feedback).toContainText('2 added.');
  await expect(feedback).toContainText('Row 3: invalid name or grade level');
  await expect(feedback).toContainText('Row 4: invalid name or grade level');
  await expect(feedback).toContainText(`Row 5: ${quotedName} is already in this section`);
  await accessibility(page);
  await dialog.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.reload();
  await expect(page.getByRole('link', { name: quotedName, exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: otherName, exact: true })).toBeVisible();
  await expect(page.getByText('2 of 2 students', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Outside Grade Range', exact: true })).toBeHidden();

  const studentsRoute = '**/api/students?**';
  await page.route(studentsRoute, (route) => route.fulfill({ status: 503, headers: { 'x-superteacher-e2e-fault': 'true' }, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic roster read failure' }) }));
  await page.reload();
  const error = page.getByRole('alert').filter({ hasText: 'Synthetic roster read failure' });
  await expect(error).toBeVisible();
  await page.unroute(studentsRoute);
  await error.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(error).toBeHidden();
  await expect(page.getByRole('link', { name: quotedName, exact: true })).toBeVisible();
  await expect(page.getByText('2 of 2 students', { exact: true })).toBeVisible();
});

test('mobile dialogs trap keyboard focus, dismiss with Escape and restore their trigger', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const trigger = page.getByRole('button', { name: '+ Course', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Add course or section' });
  await expect(dialog.getByLabel('Course name')).toBeFocused();
  await accessibility(page);
  await dialog.getByRole('button', { name: 'Create', exact: true }).focus();
  await page.keyboard.press('Tab');
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const assistantTrigger = page.getByRole('button', { name: 'Ask AI', exact: true });
  await assistantTrigger.click();
  const assistant = page.getByRole('dialog', { name: 'Super Teacher assistant' });
  await expect(assistant.getByLabel('Message')).toBeFocused();
  await accessibility(page);
  await assistant.getByRole('button', { name: 'Close assistant' }).focus();
  await page.keyboard.press('Shift+Tab');
  expect(await assistant.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(assistant).toBeHidden();
  await expect(assistantTrigger).toBeFocused();
});
