import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ConferenceSheet from '../pages/ConferenceSheet';
import { api } from '../api';
import type { StudentDetail } from '../types';
vi.mock('../api', async original => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const base: StudentDetail = { as_of: '2026-10-02', id: 's1', name: 'Ada', grade_level: 9, section_id: 'sec', section: 'Period 1', course_id: 'c', course: 'Math', average: 0, letter: 'F', gpa: 0, trend: 0, attendance_rate: 0, homework_rate: null, missing: 1, risk: 'at_risk', risk_reasons: [], attendance: [], absences: 2, tardies: 1, notes: [{ id: 'n1', body: 'Private observation', created_at: '2026-10-01' }], scores: [
  { assessment_id: 'a', title: 'Due work', kind: 'homework', due_date: '2026-10-02', max_points: 10, points: null, pct: null },
  { assessment_id: 'b', title: 'Future work', kind: 'homework', due_date: '2026-10-03', max_points: 10, points: null, pct: null },
  { assessment_id: 'c', title: 'Scored zero', kind: 'homework', due_date: '2026-10-01', max_points: 10, points: 0, pct: 0 },
] };
let response: StudentDetail;
let overflow: boolean;
beforeEach(() => {
  response = structuredClone(base); overflow = false; onlineManager.setOnline(true);
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async path => path === '/calendar' ? { today: '2026-10-02', timezone: 'UTC' } : response);
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(960);
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(() => overflow ? 1000 : 960);
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(720);
  vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockReturnValue(720);
  vi.spyOn(window, 'print').mockImplementation(() => {});
});
afterEach(() => { vi.restoreAllMocks(); onlineManager.setOnline(true); });
function Navigation() { const nav = useNavigate(); return <button onClick={() => nav('/students/s2/conference')}>Next student</button>; }
function setup(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  const tree = (current: QueryClient) => <QueryClientProvider client={current}><MemoryRouter initialEntries={['/students/s1/conference']}><Navigation /><Routes><Route path="/students/:id/conference" element={<ConferenceSheet />} /></Routes></MemoryRouter></QueryClientProvider>;
  const view = render(tree(client));
  return { client, user: userEvent.setup(), replaceClient: (next: QueryClient) => view.rerender(tree(next)) };
}
const paper = () => within(screen.getByRole('article', { name: /Conference summary for/ }));
const printButton = () => screen.getByRole('button', { name: 'Print conference sheet' });
async function loaded() { await screen.findByRole('article'); await vi.waitFor(() => expect(printButton()).toBeEnabled()); }
it('reads only student/calendar; excludes notes, future work and scored zero', async () => {
  setup(); await loaded();
  expect(paper().getByText('0% (F)')).toBeInTheDocument();
  expect(paper().getByText('0 percentage points')).toBeInTheDocument();
  expect(paper().queryByText('Private observation')).not.toBeInTheDocument();
  expect(paper().getByText(/Due work · homework/)).toBeInTheDocument();
  expect(paper().queryByText(/Future work|Scored zero/)).not.toBeInTheDocument();
  expect(vi.mocked(api).mock.calls.map(([path]) => path).sort()).toEqual(['/calendar', '/students/s1']);
});
it('prints selected notes only and allows missing-work omission', async () => {
  const { user } = setup(); await loaded();
  await user.click(screen.getByRole('checkbox', { name: 'Private observation' }));
  expect(paper().getByText('Private observation')).toBeInTheDocument();
  await user.click(screen.getByRole('checkbox', { name: /Due work/ }));
  expect(paper().queryByText(/Due work · homework/)).not.toBeInTheDocument();
  expect(paper().getByText(/1 unscored assignments.*0 included/)).toBeInTheDocument();
  await user.click(printButton()); expect(window.print).toHaveBeenCalledOnce();
});
it('preserves null and extra-credit values', async () => {
  response = { ...base, average: 112.5, trend: null, attendance_rate: null };
  setup(); await loaded(); expect(paper().getByText('112.5% (F)')).toBeInTheDocument();
  expect(paper().getAllByText('Not enough data')).toHaveLength(2);
});
for (const change of ['changed', 'removed']) it(`does not revive consent after a ${change} note returns`, async () => {
  const { client, user } = setup(); await loaded();
  await user.click(screen.getByRole('checkbox', { name: 'Private observation' }));
  await act(async () => { client.setQueryData(['student', 's1'], { ...base, notes: change === 'removed' ? [] : [{ ...base.notes[0], body: 'Changed note' }] }); });
  await vi.waitFor(() => expect(screen.queryByRole('checkbox', { name: 'Private observation' })).not.toBeInTheDocument());
  await act(async () => { client.setQueryData(['student', 's1'], base); });
  await screen.findByRole('checkbox', { name: 'Private observation' });
  expect(screen.getByRole('checkbox', { name: 'Private observation' })).not.toBeChecked();
  expect(paper().queryByText('Private observation')).not.toBeInTheDocument();
});
it('resets consent on student navigation', async () => {
  const { user } = setup(); await loaded(); await user.click(screen.getByRole('checkbox', { name: 'Private observation' }));
  response = { ...base, id: 's2', name: 'Grace' };
  await user.click(screen.getByRole('button', { name: 'Next student' }));
  await screen.findByRole('article', { name: 'Conference summary for Grace' });
  expect(screen.getByRole('checkbox', { name: 'Private observation' })).not.toBeChecked();
});
it('blocks stale school-day data until current refresh', async () => {
  response = { ...base, as_of: '2026-10-01' };
  const { user } = setup(); await screen.findByRole('article'); expect(printButton()).toBeDisabled();
  response = base; await user.click(screen.getByRole('button', { name: 'Refresh summary' }));
  await vi.waitFor(() => expect(printButton()).toBeEnabled());
});
it('hides cached record after failed refresh', async () => {
  const { user } = setup(); await loaded(); vi.mocked(api).mockRejectedValue(new Error('Read failed'));
  await user.click(screen.getByRole('button', { name: 'Refresh summary' })); await screen.findByText('Read failed');
  expect(screen.queryByRole('article')).not.toBeInTheDocument(); expect(printButton()).toBeDisabled();
});
it('rechecks fit at actual print action and blocks overflow', async () => {
  const { user } = setup(); await loaded(); overflow = true; await user.click(printButton());
  expect(window.print).not.toHaveBeenCalled(); expect(printButton()).toBeDisabled();
  expect(screen.getByRole('status')).toHaveTextContent('exceeds one page');
});
it('does not render another student returned for requested id', async () => {
  response = { ...base, id: 'wrong', name: 'Wrong student' }; setup();
  await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole('article')).not.toBeInTheDocument(); expect(printButton()).toBeDisabled();
});
it('blocks same-day cached data while offline refetch is paused', async () => {
  const client = new QueryClient(); client.setQueryData(['student', 's1'], base);
  client.setQueryData(['school-calendar'], { today: base.as_of, timezone: 'UTC' });
  onlineManager.setOnline(false); setup(client); await screen.findByRole('article');
  expect(client.getQueryState(['student', 's1'])?.fetchStatus).toBe('paused');
  expect(printButton()).toBeDisabled(); expect(api).not.toHaveBeenCalled();
});

it('requires renewed consent after query-client session replacement', async () => {
  const { user, replaceClient } = setup(); await loaded();
  await user.click(screen.getByRole('checkbox', { name: 'Private observation' }));
  replaceClient(new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  await loaded();
  expect(screen.getByRole('checkbox', { name: 'Private observation' })).not.toBeChecked();
  expect(paper().queryByText('Private observation')).not.toBeInTheDocument();
});
