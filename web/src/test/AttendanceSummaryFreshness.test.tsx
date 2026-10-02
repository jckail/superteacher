import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { useAuth } from '../auth';
import { ToastProvider } from '../components/Toast';
import Attendance from '../pages/Attendance';
import Reports from '../pages/Reports';
import type { AttendanceIn, AttendanceSheet, ClassSummary, Section, StudentPage } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
const { scope } = vi.hoisted(() => ({ scope: { section: { id: 'a', course_id: 'math', name: 'Period A' } } }));
vi.mock('../scope', () => ({ useActiveSection: () => scope.section, useScope: () => ({ ready: true, isLoading: false, setSection: vi.fn() }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => <span>Scope picker</span> }));
vi.mock('../components/ScopeStatus', () => ({ default: () => null }));

const today = '2026-10-02';
function section(id: string): Section { return { id, course_id: 'math', name: `Period ${id.toUpperCase()}` }; }
function sheet(id = 'a'): AttendanceSheet {
  return { section: section(id), day: today, rows: [{ student_id: `${id}-ada`, name: 'Ada', status: null }, { student_id: `${id}-bea`, name: 'Bea', status: null }] };
}
function summary(id = 'a', rate: number | null = null): ClassSummary {
  return { as_of: today, section_id: id, section: section(id).name, course: 'Math', students: 2, unknown: 2, on_track: 0, watch: 0, at_risk: 0, average: null, distribution: {}, assessments: [], attention: [], attendance: rate == null ? [] : [{ day: today, rate, marked: 1, absent: rate === 0 ? 1 : 0 }], attendance_rate: rate };
}
function deferred<T>() {
  let resolve!: (value: T) => void; let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function transport() {
  const sheets = new Map(['a', 'b'].map((id) => [id, sheet(id)]));
  const writes: { id: string; body: AttendanceIn; pending: ReturnType<typeof deferred<AttendanceSheet>> }[] = [];
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today } as never;
    const attendance = path.match(/^\/sections\/([^/]+)\/attendance/);
    if (attendance) {
      const id = attendance[1];
      if (options?.method === 'PUT') {
        const pending = deferred<AttendanceSheet>();
        writes.push({ id, body: options.body as AttendanceIn, pending });
        return pending.promise as never;
      }
      return sheets.get(id) as never;
    }
    const report = path.match(/^\/reports\/sections\/([^/]+)\/summary$/);
    if (report) {
      const marked = sheets.get(report[1])!.rows.filter((row) => row.status != null);
      const rate = marked.length ? marked.filter((row) => row.status === 'present' || row.status === 'tardy').length / marked.length * 100 : null;
      return summary(report[1], rate) as never;
    }
    if (path.startsWith('/students/page?')) {
      return { items: [], next_cursor: null, as_of: today, total_scoped: 0, total_matches: 0 } satisfies StudentPage as never;
    }
    throw new Error(`Unexpected fixture request ${path}`);
  });
  return {
    writes,
    async succeed(index = 0) {
      const write = writes[index]; const old = sheets.get(write.id)!;
      const next = { ...old, rows: old.rows.map((row) => ({ ...row, status: write.body.marks.find((mark) => mark.student_id === row.student_id)?.status ?? row.status })) };
      sheets.set(write.id, next);
      await act(async () => write.pending.resolve(next));
    },
    async fail(index = 0) { await act(async () => writes[index].pending.reject(new Error('Attendance unavailable'))); },
  };
}
function client() { return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } }); }
function seed(qc: QueryClient) {
  qc.setQueryData(['report-summary', 'a'], summary());
  qc.setQueryData(['report-summary', 'b'], summary('b'));
  qc.setQueryData(['report-summary', 'a', 'independent-detail'], { marker: 'unrelated descendant' });
  qc.setQueryData(['insight', 'a-ada'], { headline: 'Existing insight' });
}
function setup() {
  const qc = client(); seed(qc);
  let navigate!: ReturnType<typeof useNavigate>;
  function Navigation() { navigate = useNavigate(); return null; }
  function frame() {
    return <QueryClientProvider client={qc}><ToastProvider><MemoryRouter initialEntries={['/attendance']}><Navigation /><Routes><Route path="/attendance" element={<Attendance />} /><Route path="/reports" element={<Reports />} /></Routes></MemoryRouter></ToastProvider></QueryClientProvider>;
  }
  const view = render(frame());
  return { client: qc, user: userEvent.setup(), navigate: async (path: string) => { await act(async () => navigate(path)); }, switchSection: async (id: string) => { scope.section = section(id); view.rerender(frame()); await ready(); } };
}
async function ready() { await screen.findByRole('group', { name: 'Attendance for Ada' }); }
async function mark(user: ReturnType<typeof userEvent.setup>, status = 'Present') { await user.click(within(screen.getByRole('group', { name: 'Attendance for Ada' })).getByRole('button', { name: status })); }
function reportReads(id: string) { return vi.mocked(api).mock.calls.filter(([path]) => path === `/reports/sections/${id}/summary`); }
function attendanceStat() { return screen.getByText('Attendance', { selector: '.label' }).closest('.stat')!; }
function noGeneratedReads(qc: QueryClient) {
  expect(vi.mocked(api).mock.calls.filter(([path, options]) => path.endsWith('/insight') || options?.method === 'POST')).toHaveLength(0);
  expect(qc.getQueryState(['insight', 'a-ada'])?.isInvalidated).toBe(false);
  expect(qc.getQueryState(['report-summary', 'a', 'independent-detail'])?.isInvalidated).toBe(false);
}
beforeEach(() => { vi.mocked(api).mockReset(); scope.section = section('a'); });

it('keeps a fresh same-day cached report on navigation when no attendance was submitted', async () => {
  transport(); const { client: qc, navigate } = setup(); await ready();
  await navigate('/reports'); await screen.findByText(`Summary calculated through ${today}`);
  expect(attendanceStat()).toHaveTextContent('—');
  await navigate('/attendance'); await ready(); await navigate('/reports');
  expect(reportReads('a')).toHaveLength(0);
  expect(qc.getQueryState(['report-summary', 'a'])?.isInvalidated).toBe(false);
  noGeneratedReads(qc);
});

it.each(['stay', 'switch', 'ABA'] as const)('refreshes the submitted section report after success while scope transition is %s', async (transition) => {
  const fixture = transport(); const { client: qc, user, navigate, switchSection } = setup(); await ready();
  const other = qc.getQueryData(['report-summary', 'b']);
  await mark(user); await waitFor(() => expect(fixture.writes).toHaveLength(1));
  expect(fixture.writes[0].id).toBe('a');
  expect(fixture.writes[0].body).toEqual({ day: today, marks: [{ student_id: 'a-ada', status: 'present' }] });
  expect(qc.getQueryState(['report-summary', 'a'])?.isInvalidated).toBe(false);
  if (transition !== 'stay') await switchSection('b');
  if (transition === 'ABA') await switchSection('a');
  await fixture.succeed();
  await waitFor(() => expect(qc.getQueryState(['report-summary', 'a'])?.isInvalidated).toBe(true));
  expect(qc.getQueryState(['report-summary', 'b'])?.isInvalidated).toBe(false);
  expect(qc.getQueryData(['report-summary', 'b'])).toBe(other);
  if (transition === 'switch') {
    await navigate('/reports'); await screen.findByText(`Summary calculated through ${today}`);
    expect(reportReads('b')).toHaveLength(0); expect(attendanceStat()).toHaveTextContent('—');
    await navigate('/attendance'); await switchSection('a');
  }
  await navigate('/reports');
  await waitFor(() => expect(attendanceStat()).toHaveTextContent('100%'));
  expect(screen.getByRole('img', { name: /Daily attendance rate.*100 percent/ })).toBeInTheDocument();
  expect(reportReads('a')).toHaveLength(1); expect(reportReads('a')[0][1]?.signal).toBeInstanceOf(AbortSignal);
  expect(qc.getQueryData<ClassSummary>(['report-summary', 'a'])?.attendance_rate).toBe(100);
  expect(fixture.writes).toHaveLength(1); noGeneratedReads(qc);
});

it('reconciles a failed save and refreshes only its report without keeping optimistic attendance', async () => {
  const fixture = transport(); const { client: qc, user, navigate } = setup(); await ready();
  await mark(user); await waitFor(() => expect(fixture.writes).toHaveLength(1));
  expect(within(screen.getByRole('group', { name: 'Attendance for Ada' })).getByRole('button', { name: 'Present' })).toHaveAttribute('aria-pressed', 'true');
  await fixture.fail(); await screen.findByText('Couldn’t save attendance: Attendance unavailable');
  await waitFor(() => expect(qc.getQueryState(['report-summary', 'a'])?.isInvalidated).toBe(true));
  expect(within(screen.getByRole('group', { name: 'Attendance for Ada' })).getByRole('button', { name: 'Present' })).toHaveAttribute('aria-pressed', 'false');
  await navigate('/reports'); await waitFor(() => expect(reportReads('a')).toHaveLength(1));
  expect(attendanceStat()).toHaveTextContent('—');
  expect(qc.getQueryState(['report-summary', 'b'])?.isInvalidated).toBe(false);
  expect(fixture.writes).toHaveLength(1); noGeneratedReads(qc);
});

it('keeps serialized later optimism through an earlier failure and reports the final committed mark', async () => {
  const fixture = transport(); const { client: qc, user, navigate } = setup(); await ready();
  await mark(user); await waitFor(() => expect(fixture.writes).toHaveLength(1));
  await mark(user, 'Absent');
  await waitFor(() => expect(qc.isMutating({ mutationKey: ['attendance-save'] })).toBe(2));
  expect(fixture.writes).toHaveLength(1);
  await fixture.fail(); await waitFor(() => expect(fixture.writes).toHaveLength(2));
  expect(within(screen.getByRole('group', { name: 'Attendance for Ada' })).getByRole('button', { name: 'Absent' })).toHaveAttribute('aria-pressed', 'true');
  await fixture.succeed(1); await waitFor(() => expect(qc.isMutating()).toBe(0));
  await navigate('/reports'); await waitFor(() => expect(attendanceStat()).toHaveTextContent('0%'));
  expect(qc.getQueryData<ClassSummary>(['report-summary', 'a'])?.attendance[0].absent).toBe(1);
  expect(reportReads('a')).toHaveLength(1); noGeneratedReads(qc);
});

it('refreshes the class summary after the existing bulk present action', async () => {
  const fixture = transport(); const { client: qc, user, navigate } = setup(); await ready();
  await user.click(screen.getByRole('button', { name: 'Mark 2 unmarked present' }));
  await waitFor(() => expect(fixture.writes).toHaveLength(1));
  expect(fixture.writes[0].body.marks).toEqual([{ student_id: 'a-ada', status: 'present' }, { student_id: 'a-bea', status: 'present' }]);
  await fixture.succeed(); await screen.findByText('Marked 2 students present');
  await navigate('/reports'); await waitFor(() => expect(attendanceStat()).toHaveTextContent('100%'));
  expect(reportReads('a')).toHaveLength(1); noGeneratedReads(qc);
});

let Root: typeof import('../main')['Root'];
beforeAll(async () => {
  const root = document.createElement('div'); root.id = 'root'; document.body.append(root);
  try { ({ Root } = await import('../main')); } finally { root.remove(); }
});

it('settles a previous session save on its original client without invalidating the new same-section session', async () => {
  const fixture = transport(); const ordinary = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/auth/login' || path === '/auth/logout') return {} as never;
    return ordinary(path, options);
  });
  const clients: QueryClient[] = []; let logout!: () => void;
  function Session() {
    const qc = useQueryClient(); if (!clients.includes(qc)) { qc.setDefaultOptions({ queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } }); seed(qc); clients.push(qc); }
    logout = useAuth().logout;
    return <ToastProvider><MemoryRouter><Attendance /></MemoryRouter></ToastProvider>;
  }
  render(<Root><Session /></Root>); const user = userEvent.setup(); await ready();
  const old = clients.at(-1)!; const oldInvalidation = vi.spyOn(old, 'invalidateQueries');
  await mark(user); await waitFor(() => expect(fixture.writes).toHaveLength(1));
  await act(async () => logout()); await screen.findByRole('heading', { name: 'Sign in' });
  expect(old.getQueryCache().getAll()).toHaveLength(0);
  await user.type(screen.getByLabelText('Passcode'), 'next-session'); await user.click(screen.getByRole('button', { name: 'Sign in' })); await ready();
  const current = clients.at(-1)!; expect(current).not.toBe(old);
  const currentInvalidation = vi.spyOn(current, 'invalidateQueries');
  const newSummary = current.getQueryData(['report-summary', 'a']);
  await fixture.succeed();
  await waitFor(() => expect(oldInvalidation.mock.calls.some(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(['report-summary', 'a']))).toBe(true));
  expect(currentInvalidation).not.toHaveBeenCalled();
  expect(current.getQueryData(['report-summary', 'a'])).toBe(newSummary);
  expect(current.getQueryState(['report-summary', 'a'])?.isInvalidated).toBe(false);
  expect(old.getQueryCache().getAll()).toHaveLength(0);
  expect(reportReads('a')).toHaveLength(0); expect(fixture.writes).toHaveLength(1);
});
