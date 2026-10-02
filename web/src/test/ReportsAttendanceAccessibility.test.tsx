import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import Reports from '../pages/Reports';
import type { AttendanceDay, ClassSummary } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
const { scope } = vi.hoisted(() => ({ scope: { ready: true } }));
vi.mock('../scope', () => ({
  useActiveSection: () => scope.ready ? { id: 'p1', course_id: 'math', name: 'P1' } : undefined,
  useScope: () => ({ ready: scope.ready, isLoading: false, setSection: vi.fn() }),
}));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
vi.mock('../components/ScopeStatus', () => ({ default: () => null }));

const days: AttendanceDay[] = [
  { day: '2026-09-30', rate: 66.7, marked: 4, absent: 1 },
  { day: '2026-10-01', rate: 0, marked: 2, absent: 2 },
  { day: '2026-10-02', rate: null, marked: 3, absent: 0 },
];
function summary(attendance = days): ClassSummary {
  return { as_of: '2026-10-02', section_id: 'p1', section: 'P1', course: 'Math', students: 4,
    unknown: 4, on_track: 0, watch: 0, at_risk: 0, average: null, distribution: {},
    assessments: [], attention: [], attendance, attendance_rate: null };
}
function setup(attendance = days) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { today: '2026-10-02', timezone: 'America/Los_Angeles' } as never;
    if (path.endsWith('/summary')) return summary(attendance) as never;
    if (path.startsWith('/students/page')) return { items: [], next_cursor: null, total_matches: 0, total_scoped: 0, as_of: '2026-10-02' } as never;
    throw new Error('Unexpected synthetic request');
  });
  const frame = () => <QueryClientProvider client={client}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>;
  return { ...render(frame()), client, frame, user: userEvent.setup() };
}
async function openNumbers(user: ReturnType<typeof userEvent.setup>) {
  const toggle = await screen.findByText('Show attendance numbers');
  await user.click(toggle);
  return screen.getByRole('table', { name: 'Daily attendance numbers' });
}
beforeEach(() => { vi.mocked(api).mockReset(); scope.ready = true; });

it('provides full dates, fractional rates and counts beyond chart color and tooltips', async () => {
  const { user } = setup();
  const table = await openNumbers(user);
  for (const header of ['Date', 'Attendance rate', 'Marked', 'Absent']) {
    expect(within(table).getByRole('columnheader', { name: header })).toBeInTheDocument();
  }
  const row = within(table).getByRole('rowheader', { name: '2026-09-30' }).closest('tr')!;
  expect(within(row).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['66.7%', '4', '1']);
  expect(screen.getByText(/Present and tardy count as attended; excused absences are excluded from the rate/)).toBeInTheDocument();
  expect(screen.getByText(/Marked includes all recorded attendance statuses/)).toBeInTheDocument();
});

it('distinguishes zero attendance from an unavailable rate', async () => {
  const { user } = setup();
  const table = await openNumbers(user);
  const zero = within(table).getByRole('rowheader', { name: '2026-10-01' }).closest('tr')!;
  const unavailable = within(table).getByRole('rowheader', { name: '2026-10-02' }).closest('tr')!;
  expect(within(zero).getAllByRole('cell')[0]).toHaveTextContent(/^0%$/);
  expect(within(unavailable).getAllByRole('cell')[0]).toHaveTextContent(/^Not available$/);
  expect(within(unavailable).getAllByRole('cell')[1]).toHaveTextContent(/^3$/);
});

it('keeps both chart and numbers scrollers keyboard focusable and opens without any write', async () => {
  const { user } = setup();
  await openNumbers(user);
  const chart = screen.getByRole('region', { name: 'Daily attendance chart' });
  const numbers = screen.getByRole('region', { name: 'Daily attendance numbers' });
  expect(chart).toHaveAttribute('tabindex', '0');
  numbers.focus();
  expect(numbers).toHaveFocus();
  expect(numbers).toHaveAttribute('tabindex', '0');
  await user.click(screen.getByText('Show attendance numbers'));
  expect(numbers.closest('details')).not.toHaveAttribute('open');
  expect(numbers).not.toBeVisible();
  expect(vi.mocked(api).mock.calls.every(([, options]) => !options?.method || options.method === 'GET')).toBe(true);
});

it('updates the disclosed numbers from the current summary instead of a copied snapshot', async () => {
  const { user, client } = setup();
  await openNumbers(user);
  await act(async () => { client.setQueryData(['report-summary', 'p1'], summary([{ day: '2026-10-02', rate: 100, marked: 4, absent: 0 }])); });
  const table = screen.getByRole('table', { name: 'Daily attendance numbers' });
  await waitFor(() => expect(within(table).queryByRole('rowheader', { name: '2026-09-30' })).not.toBeInTheDocument());
  expect(within(table).getAllByRole('row')).toHaveLength(2);
  expect(within(table).getByRole('cell', { name: '100%' })).toBeInTheDocument();
});

it('hides cached attendance when the saved scope is unresolved', async () => {
  const { user, rerender, frame } = setup();
  await openNumbers(user);
  scope.ready = false;
  rerender(frame());
  expect(screen.queryByRole('table', { name: 'Daily attendance numbers' })).not.toBeInTheDocument();
  expect(screen.queryByText('Show attendance numbers')).not.toBeInTheDocument();
});

it('retains the empty state without an empty disclosure', async () => {
  setup([]);
  expect(await screen.findByText('No attendance recorded in the last 30 days.')).toBeInTheDocument();
  expect(screen.queryByText('Show attendance numbers')).not.toBeInTheDocument();
});
