import { test, expect } from '../support/fixtures';

test.describe('roster search / filter / sort (seeded classroom)', () => {
  test('search narrows the list and lives in the URL', async ({ page, api }) => {
    const all = await api.students();
    const target = all[3].name.split(' ')[0];
    await page.goto('/roster');
    await expect(page.getByText(`${all.length} of ${all.length} students`)).toBeVisible();
    await page.getByLabel('Search students').fill(target);
    await expect(page).toHaveURL(new RegExp(`q=${target}`));
    const expected = all.filter((s) => s.name.toLowerCase().includes(target.toLowerCase())).length;
    await expect(page.getByText(`${expected} of ${all.length} students`)).toBeVisible();

    await page.reload(); // URL state survives
    await expect(page.getByLabel('Search students')).toHaveValue(target);
    await expect(page.getByText(`${expected} of ${all.length} students`)).toBeVisible();

    await page.getByLabel('Search students').fill('zzzz-nobody');
    await expect(page.getByText('No students match.')).toBeVisible();
    await page.getByRole('button', { name: 'Clear filters' }).first().click();
    await expect(page).not.toHaveURL(/q=/);
    await expect(page.getByText(`${all.length} of ${all.length} students`)).toBeVisible();
  });

  test('status filter matches the API risk classification and is shareable by URL', async ({ page, api }) => {
    const all = await api.students();
    const atRisk = all.filter((s) => s.risk === 'at_risk').length;
    expect(atRisk).toBeGreaterThan(0);
    await page.goto('/roster');
    await page.getByRole('group', { name: 'Filter by status' }).getByRole('button', { name: 'At risk' }).click();
    await expect(page).toHaveURL(/status=at_risk/);
    await expect(page.getByText(`${atRisk} of ${all.length} students`)).toBeVisible();
    const chips = page.locator('tbody .chip');
    await expect(chips).toHaveCount(Math.min(atRisk, 50));
    for (const t of await chips.allTextContents()) expect(t).toBe('At risk');

    await page.goto('/roster?status=on_track&q=a');
    await expect(page.getByRole('button', { name: 'On track', pressed: true })).toBeVisible();
    await expect(page.getByLabel('Search students')).toHaveValue('a');
  });

  test('sorting by name toggles direction, reflected in aria-sort and URL', async ({ page, api }) => {
    const all = await api.students();
    const names = all.map((s) => s.name.toLowerCase()).sort();
    await page.goto('/roster');
    const header = page.getByRole('columnheader', { name: /Student/ });
    await header.getByRole('button').click();
    await expect(header).toHaveAttribute('aria-sort', 'ascending');
    await expect(page).toHaveURL(/sort=name/);
    const first = page.locator('tbody tr').first().locator('a.row-link');
    await expect(first).toHaveText(new RegExp(`^${names[0]}$`, 'i'));
    await header.getByRole('button').click();
    await expect(header).toHaveAttribute('aria-sort', 'descending');
    await expect(page).toHaveURL(/dir=desc/);
    await expect(first).toHaveText(new RegExp(`^${names.at(-1)}$`, 'i'));

    await page.reload();
    await expect(header).toHaveAttribute('aria-sort', 'descending');
    await expect(first).toHaveText(new RegExp(`^${names.at(-1)}$`, 'i'));
  });

  test('clicking a row opens that student', async ({ page, api }) => {
    const all = await api.students();
    await page.goto('/roster');
    await page.getByLabel('Search students').fill(all[0].name);
    await page.locator('tbody tr').first().locator('td').nth(2).click();
    await expect(page).toHaveURL(new RegExp(`/students/${all[0].id}`));
  });
  test('cursor pages load on demand with bounded rows and restart legacy page links', async ({ page, api }) => {
    const sample = (await api.students())[0];
    const students = Array.from({ length: 101 }, (_, i) => ({ ...sample, id: `cursor-${i}`, name: `Cursor Student ${String(i).padStart(3, '0')}` }));
    const requests: { url: string; cursor: string | undefined }[] = [];
    await page.route('**/api/students/page?*', async (route) => {
      const request = route.request();
      const cursor = request.headers()['x-roster-cursor'];
      requests.push({ url: request.url(), cursor });
      const offset = cursor === 'owned-name-page-2' ? 50 : cursor === 'owned-name-page-3' ? 100 : 0;
      await route.fulfill({ json: { items: students.slice(offset, offset + 50), next_cursor: offset === 0 ? 'owned-name-page-2' : offset === 50 ? 'owned-name-page-3' : null, as_of: '2026-10-02', total_matches: 101, total_scoped: 101 } });
    });
    await page.goto('/roster?sort=name&page=999');
    await expect(page.getByText('101 of 101 students')).toBeVisible();
    await expect(page.getByText(/Roster page links now start at the first page/)).toBeVisible();
    await expect(page).not.toHaveURL(/page=/);
    await expect(page.locator('tbody a.row-link')).toHaveCount(50);
    expect(requests).toHaveLength(1);
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect(page.locator('tbody a.row-link').first()).toHaveText('Cursor Student 050');
    expect(requests[1].cursor).toBe('owned-name-page-2');
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect(page.locator('tbody a.row-link')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Next page' })).toBeDisabled();
    await page.getByRole('button', { name: 'Previous page' }).click();
    await expect(page.locator('tbody a.row-link').first()).toHaveText('Cursor Student 050');
    expect(requests[3].cursor).toBe('owned-name-page-2');
    expect(requests.every((r) => !r.url.includes('owned-name'))).toBe(true);
    await page.reload();
    await expect(page.locator('tbody a.row-link').first()).toHaveText('Cursor Student 000');
    expect(requests.at(-1)?.cursor).toBeUndefined();
    await expect(page.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  });

});
