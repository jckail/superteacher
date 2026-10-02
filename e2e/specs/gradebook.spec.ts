import { test, expect, uid, useClassroom } from '../support/fixtures';

test.describe('gradebook', () => {
  test('add an assignment, enter scores, values persist after reload', async ({ page, api }) => {
    const names = [uid('Ann '), uid('Bob '), uid('Cy ')];
    const c = await api.classroom({ studentNames: names });
    await useClassroom(page, c);
    await page.goto('/gradebook');
    await expect(page.getByText('No assignments yet')).toBeVisible();

    await page.getByRole('button', { name: '+ New assignment' }).click();
    const dialog = page.getByRole('dialog', { name: 'New assignment' });
    await dialog.getByLabel('Title').fill('Quiz 1');
    await dialog.getByLabel('Type').selectOption('quiz');
    await dialog.getByLabel('Max points').fill('20');
    await dialog.getByRole('button', { name: 'Create' }).click();
    await expect(page.getByText('Added “Quiz 1”')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Quiz 1' })).toBeVisible();

    const cell = (n: string) => page.getByRole('textbox', { name: `${n}, Quiz 1` });
    await cell(names[0]).fill('18');
    await cell(names[0]).press('Tab');
    await expect(page.getByText(`Saved ${names[0]} · Quiz 1`)).toBeVisible();
    await cell(names[1]).fill('12.5');
    await cell(names[1]).blur();
    await expect(page.getByText(`Saved ${names[1]} · Quiz 1`)).toBeVisible();

    await page.reload();
    await expect(cell(names[0])).toHaveValue('18');
    await expect(cell(names[1])).toHaveValue('12.5');
    await expect(cell(names[2])).toHaveValue('');
    // server agrees
    const gb = await api.gradebook(c.sectionId);
    const byName = Object.fromEntries(gb.rows.map((r: any) => [r.name, Object.values(r.points)[0]]));
    expect(byName[names[0]]).toBe(18);
    expect(byName[names[1]]).toBe(12.5);
    expect(byName[names[2]] ?? null).toBeNull();
  });

  test('over-max score is flagged but allowed (extra credit); invalid input is rejected', async ({ page, api }) => {
    const n = uid('Dee ');
    const c = await api.classroom({ studentNames: [n] });
    await api.assessment(c.sectionId, 'HW 1', 10);
    await useClassroom(page, c);
    await page.goto('/gradebook');
    const cell = page.getByRole('textbox', { name: `${n}, HW 1` });
    await cell.fill('15');
    await expect(page.getByText('Over 10')).toBeVisible();
    await cell.blur();
    await expect(page.getByText(`Saved ${n} · HW 1`)).toBeVisible();

    await cell.fill('abc');
    await expect(page.getByText('Enter a number ≥ 0')).toBeVisible();
    await expect(cell).toHaveAttribute('aria-invalid', 'true');
    await cell.blur();
    await expect(cell).toHaveValue('15'); // reverted, nothing bad saved
    await page.reload();
    await expect(page.getByRole('textbox', { name: `${n}, HW 1` })).toHaveValue('15');
  });

  test('keyboard: Enter and arrows move between rows, Esc undoes', async ({ page, api }) => {
    const names = ['Aaa', 'Bbb', 'Ccc'].map((p) => `${p} ${uid()}`);
    const c = await api.classroom({ studentNames: names });
    await api.assessment(c.sectionId, 'HW 1', 10);
    await useClassroom(page, c);
    await page.goto('/gradebook');
    const cell = (i: number) => page.getByRole('textbox', { name: `${names[i]}, HW 1` });

    await cell(0).click();
    await cell(0).fill('7');
    await page.keyboard.press('Enter');
    await expect(cell(1)).toBeFocused();
    await page.keyboard.type('8');
    await page.keyboard.press('ArrowDown');
    await expect(cell(2)).toBeFocused();
    await page.keyboard.type('9');
    await page.keyboard.press('ArrowUp');
    await expect(cell(1)).toBeFocused();
    await page.keyboard.press('ArrowUp');
    await expect(cell(0)).toBeFocused();

    await page.keyboard.type('3'); // selected on focus -> replaces 7
    await page.keyboard.press('Escape');
    await expect(cell(0)).toHaveValue('7');

    await page.reload();
    await expect(cell(0)).toHaveValue('7');
    await expect(cell(1)).toHaveValue('8');
    await expect(cell(2)).toHaveValue('9');
  });
});
