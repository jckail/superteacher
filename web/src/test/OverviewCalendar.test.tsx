import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, UNAUTHORIZED_EVENT } from '../api';
import { AuthGate, clearPrivateSession } from '../auth';
import Overview from '../pages/Overview';
import type { Overview as OverviewData } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
const { scope } = vi.hoisted(() => ({ scope: { ready: true, course: undefined as { id: string } | undefined, section: undefined as { id: string } | undefined } }));
vi.mock('../scope', () => ({ useScope: () => scope }));
vi.mock('../components/ScopePicker', () => ({ default: () => <span>Scope picker</span> }));
vi.mock('../components/ScopeStatus', () => ({ default: () => scope.ready ? null : <p>Resolve saved scope</p> }));

function overview(day = '2026-09-30'): OverviewData & { as_of: string } {
  const due = day >= '2026-10-01';
  return { as_of: day, students: 1, average: due ? 90 : null, attendance_rate: null, homework_rate: null, unknown: due ? 0 : 1, on_track: due ? 1 : 0, watch: 0, at_risk: 0, distribution: { A: due ? 1 : 0, B: 0, C: 0, D: 0, F: 0 }, attention: [] };
}
function client() { return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }); }
function frame(qc: QueryClient, children: ReactNode = <Overview />) { return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>; }
function setup(qc = client()) { return { ...render(frame(qc)), client: qc, user: userEvent.setup() }; }
function reads() { return vi.mocked(api).mock.calls.filter(([path]) => path.startsWith('/overview')); }
async function day(qc: QueryClient, today = '2026-10-01') { await act(async () => { qc.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today }); }); }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function stat(label: string) { return screen.getByText(label).closest('.stat')!; }
beforeEach(() => { vi.mocked(api).mockReset(); scope.ready = true; scope.course = undefined; scope.section = undefined; });

it('refreshes rendered progress once after a validated school-day change while preserving the original scope key', async () => {
  let today = '2026-09-30';
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today } : overview(today)) as never);
  const { client: qc } = setup();
  await screen.findByText('Record work or attendance before assessing progress.');
  expect(stat('Class average')).toHaveTextContent('—');
  today = '2026-10-01'; await day(qc);
  await waitFor(() => expect(reads()).toHaveLength(2));
  await waitFor(() => expect(stat('Class average')).toHaveTextContent('90%'));
  expect(screen.getByText('Everyone is on track.')).toBeInTheDocument();
  expect(within(screen.getByRole('table', { name: 'Grade distribution' })).getByRole('row', { name: 'A 1' })).toBeInTheDocument();
  expect(screen.getByText('Progress calculated through 2026-10-01')).toBeInTheDocument();
  expect(qc.getQueryData<OverviewData>(['overview', undefined, undefined])?.unknown).toBe(0);
  expect(qc.getQueryCache().find({ queryKey: ['overview', undefined, undefined], exact: true })?.queryKey).toEqual(['overview', undefined, undefined]);
  await day(qc); expect(reads()).toHaveLength(2);
});

it('retains the failed cutoff and evidence until an explicit progress retry succeeds', async () => {
  let fail = true;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (reads().length > 1 && fail) throw new Error('Progress read failed');
    return overview(reads().length > 1 ? '2026-10-01' : '2026-09-30') as never;
  });
  const { client: qc, user } = setup();
  await screen.findByText('Progress calculated through 2026-09-30');
  await day(qc);
  await screen.findByText('Progress read failed');
  expect(screen.getByText('Progress calculated through 2026-09-30')).toBeInTheDocument();
  expect(screen.getByText(/Refresh failed. Use Retry to update progress/)).toHaveAttribute('role', 'status');
  expect(screen.getByText('Record work or attendance before assessing progress.')).toBeInTheDocument();
  expect(screen.queryByText('No students yet')).not.toBeInTheDocument();
  await day(qc); expect(reads()).toHaveLength(2);
  fail = false; await user.click(screen.getByRole('button', { name: /^Retry$/ }));
  await screen.findByText('Progress calculated through 2026-10-01');
  expect(stat('Class average')).toHaveTextContent('90%');
  expect(reads()).toHaveLength(3);
});

it.each(['fresh', 'older'] as const)('coalesces day advancement during a mutation-invalidated read with a %s response', async (result) => {
  const pending = deferred<OverviewData>();
  let manual = false;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (reads().length === 2) return pending.promise as never;
    return overview(manual ? '2026-10-01' : '2026-09-30') as never;
  });
  const { client: qc, user } = setup();
  await screen.findByText('Progress calculated through 2026-09-30');
  await act(async () => { void qc.invalidateQueries({ queryKey: ['overview'] }); });
  await waitFor(() => expect(reads()).toHaveLength(2));
  await day(qc);
  await screen.findByText(/Updating school-day calculations/);
  expect(reads()).toHaveLength(2);
  await act(async () => pending.resolve(overview(result === 'fresh' ? '2026-10-01' : '2026-09-30')));
  if (result === 'fresh') {
    await screen.findByText('Progress calculated through 2026-10-01');
    expect(reads()).toHaveLength(2);
    expect(stat('Class average')).toHaveTextContent('90%');
  } else {
    await screen.findByRole('button', { name: 'Refresh progress' });
    expect(reads()).toHaveLength(3); // One attempt after the earlier read returned its old cutoff.
    await day(qc); expect(reads()).toHaveLength(3);
    expect(screen.getByText('Progress calculated through 2026-09-30')).toBeInTheDocument();
    manual = true; await user.click(screen.getByRole('button', { name: 'Refresh progress' }));
    await screen.findByText('Progress calculated through 2026-10-01');
    expect(reads()).toHaveLength(4);
  }
});

it.each(['scope', 'readiness'] as const)('resets the bounded attempt after a %s ABA transition back to the same stale IDs', async (transition) => {
  scope.course = { id: 'a' }; scope.section = { id: 's' };
  let aReads = 0;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (path.includes('course_id=a')) return overview(++aReads >= 3 ? '2026-10-01' : '2026-09-30') as never;
    return overview('2026-10-01') as never;
  });
  const { client: qc, rerender } = setup();
  await screen.findByText('Progress calculated through 2026-09-30');
  await day(qc);
  await screen.findByRole('button', { name: 'Refresh progress' });
  expect(aReads).toBe(2);
  if (transition === 'scope') scope.course = { id: 'b' };
  else scope.ready = false;
  rerender(frame(qc));
  if (transition === 'scope') await screen.findByText('Progress calculated through 2026-10-01');
  else {
    await screen.findByText('Resolve saved scope');
    expect(screen.queryByText(/Progress calculated through/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Refresh progress' })).not.toBeInTheDocument();
  }
  scope.course = { id: 'a' }; scope.ready = true;
  rerender(frame(qc));
  await waitFor(() => expect(aReads).toBe(3));
  await screen.findByText('Progress calculated through 2026-10-01');
  expect(qc.getQueryData<OverviewData>(['overview', 'a', 's'])?.average).toBe(90);
  await day(qc); expect(aReads).toBe(3);
});

it('aborts a superseded scope read and rejects its late result even after returning to the original scope', async () => {
  scope.course = { id: 'a' };
  const pending = deferred<OverviewData>();
  let aReads = 0, signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (path.includes('course_id=a')) {
      if (++aReads === 1) return overview() as never;
      if (aReads === 2) { signal = options?.signal; return pending.promise as never; }
    }
    return overview('2026-10-01') as never;
  });
  const { client: qc, rerender } = setup();
  await screen.findByText('Progress calculated through 2026-09-30');
  await day(qc); await waitFor(() => expect(aReads).toBe(2));
  scope.course = { id: 'b' }; rerender(frame(qc));
  await screen.findByText('Progress calculated through 2026-10-01');
  expect(signal?.aborted).toBe(true);
  scope.course = { id: 'a' }; rerender(frame(qc));
  await waitFor(() => expect(aReads).toBe(3));
  await screen.findByText('Progress calculated through 2026-10-01');
  await act(async () => pending.resolve(overview('2026-09-30')));
  expect(stat('Class average')).toHaveTextContent('90%');
  expect(qc.getQueryData<OverviewData>(['overview', 'a', undefined])?.as_of).toBe('2026-10-01');
});

it('keeps a newer server cutoff even when the school calendar is briefly older', async () => {
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: '2026-09-30' } : overview('2026-10-01')) as never);
  const { client: qc } = setup();
  await screen.findByText('Progress calculated through 2026-10-01');
  expect(screen.queryByRole('button', { name: 'Refresh progress' })).not.toBeInTheDocument();
  await day(qc, '2026-09-30'); expect(reads()).toHaveLength(1);
});

it('shows the response cutoff without a calendar fallback and gates calendar recovery on readiness', async () => {
  let fail = true;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') { if (fail) throw new Error('Calendar unavailable'); return { timezone: 'America/Los_Angeles', today: '2000-01-01' } as never; }
    return overview('2000-01-01') as never;
  });
  const { client: qc, user, rerender } = setup();
  await screen.findByText('Progress calculated through 2000-01-01');
  await screen.findByText('Calendar unavailable');
  expect(reads()).toHaveLength(1);
  scope.ready = false; rerender(frame(qc));
  expect(screen.queryByText('Calendar unavailable')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Retry school calendar' })).not.toBeInTheDocument();
  scope.ready = true; rerender(frame(qc));
  await screen.findByRole('button', { name: 'Retry school calendar' });
  fail = false; await user.click(screen.getByRole('button', { name: 'Retry school calendar' }));
  await waitFor(() => expect(screen.queryByText('Calendar unavailable')).not.toBeInTheDocument());
  expect(screen.getByText('Progress calculated through 2000-01-01')).toBeInTheDocument();
  expect(reads()).toHaveLength(1);
});

it('labels a genuine empty response and revalidates an old cache when reopened', async () => {
  const qc = client();
  const empty = { ...overview(), students: 0, unknown: 0 };
  qc.setQueryData(['overview', undefined, undefined], empty);
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: '2026-10-01' } : { ...empty, as_of: '2026-10-01' }) as never);
  setup(qc);
  await screen.findByText('No students yet');
  await screen.findByText('Progress calculated through 2026-10-01');
  expect(reads()).toHaveLength(1);
  expect(screen.queryByText('Everyone is on track.')).not.toBeInTheDocument();
  expect(qc.getQueryData<OverviewData>(['overview', undefined, undefined])?.students).toBe(0);
});

it('makes no calendar or data read until saved scope is ready', async () => {
  scope.ready = false;
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: '2026-09-30' } : overview()) as never);
  const { client: qc, rerender } = setup();
  expect(screen.getByText('Resolve saved scope')).toBeInTheDocument();
  expect(api).not.toHaveBeenCalled();
  scope.ready = true; scope.course = { id: 'a' }; scope.section = { id: 's' };
  rerender(frame(qc));
  await screen.findByText('Progress calculated through 2026-09-30');
  expect(reads()).toHaveLength(1);
  expect(reads()[0][0]).toBe('/overview?course_id=a&section_id=s');
});

it('clears pending private progress on auth teardown and ignores its late response', async () => {
  const pending = deferred<OverviewData>();
  let count = 0, signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { auth_required: true } as never;
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (++count === 1) return overview() as never;
    signal = options?.signal; return pending.promise as never;
  });
  const qc = client();
  render(frame(qc, <AuthGate onLogout={() => clearPrivateSession(qc)}><Overview /></AuthGate>));
  await screen.findByText('Progress calculated through 2026-09-30');
  await day(qc); await waitFor(() => expect(count).toBe(2));
  await act(async () => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
  expect(signal?.aborted).toBe(true);
  expect(screen.queryByText(/Progress calculated through/)).not.toBeInTheDocument();
  await act(async () => pending.resolve(overview('2026-10-01')));
  expect(qc.getQueryData(['overview', undefined, undefined])).toBeUndefined();
});
