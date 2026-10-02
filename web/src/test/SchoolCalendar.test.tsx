import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, UNAUTHORIZED_EVENT } from '../api';
import { AuthGate, clearPrivateSession } from '../auth';
import { ToastProvider } from '../components/Toast';
import { ConfirmProvider } from '../components/Confirm';
import Attendance from '../pages/Attendance';
import Gradebook, { NewAssessment } from '../pages/Gradebook';
import Student from '../pages/Student';
import type { Gradebook as GradebookData, StudentDetail } from '../types';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const { scope } = vi.hoisted(() => ({ scope: { ready: true, section: { id: 'class', course_id: 'math', name: 'Math' } } }));
vi.mock('../scope', () => ({ useActiveSection: () => scope.ready ? scope.section : undefined, useScope: () => ({ isLoading: false, ready: scope.ready }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
function setup(page: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}>{page}</MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  return { ...view, client, user: userEvent.setup() };
}
beforeEach(() => { vi.mocked(api).mockReset(); scope.ready = true; scope.section = { id: 'class', course_id: 'math', name: 'Math' }; });

it('uses the school date for attendance and preserves a manually selected day across midnight', async () => {
  vi.mocked(api).mockImplementation(async (path) => path === '/calendar'
    ? { timezone: 'America/Los_Angeles', today: '2026-09-30' }
    : { section: { id: 'class', course_id: 'math', name: 'Math' }, day: path.split('day=')[1], rows: [] });
  const { client } = setup(<Attendance />);
  const date = await screen.findByLabelText('Date');
  expect(date).toHaveValue('2026-09-30');
  expect(date).toHaveAttribute('max', '2026-09-30');
  expect(api).toHaveBeenCalledWith('/sections/class/attendance?day=2026-09-30', { signal: expect.any(AbortSignal) });
  fireEvent.change(date, { target: { value: '2026-09-29' } });
  await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/sections/class/attendance?day=2026-09-29', { signal: expect.any(AbortSignal) }));
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-01' }); });
  // React Query notifies subscribers asynchronously after the cache update.
  await waitFor(() => {
    expect(date).toHaveAttribute('max', '2026-10-01');
    expect(date).toHaveValue('2026-09-29');
  });
});

it('does not request or show attendance with an unavailable school calendar', async () => {
  vi.mocked(api).mockRejectedValue(new Error('Calendar unavailable'));
  setup(<Attendance />);
  expect((await screen.findByText('Calendar unavailable')).closest('[role="alert"]')).toBeInTheDocument();
  expect(screen.queryByLabelText('Date')).not.toBeInTheDocument();
  expect(vi.mocked(api).mock.calls.every(([path]) => path === '/calendar')).toBe(true);
});

it('creates a fractional-point assignment on the school date and holds the dialog while saving', async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(api).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const close = vi.fn();
  const { user } = setup(<NewAssessment sectionId="class" schoolDay="2026-09-30" onClose={close} />);
  expect(screen.getByLabelText('Due')).toHaveValue('2026-09-30');
  await user.type(screen.getByLabelText('Title'), 'Half point');
  await user.clear(screen.getByLabelText('Max points'));
  await user.type(screen.getByLabelText('Max points'), '0');
  expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
  await user.clear(screen.getByLabelText('Max points'));
  await user.type(screen.getByLabelText('Max points'), '0.5');
  await user.click(screen.getByRole('button', { name: 'Create' }));
  expect(api).toHaveBeenCalledWith('/sections/class/assessments', { method: 'POST', body: { title: 'Half point', kind: 'homework', max_points: 0.5, due_date: '2026-09-30' } });
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  await user.keyboard('{Escape}');
  expect(close).not.toHaveBeenCalled();
  await act(async () => { finish({ as_of: '2026-09-30', section: { id: 'class', course_id: 'math', name: 'Math' }, assessments: [], rows: [] }); });
  await vi.waitFor(() => expect(close).toHaveBeenCalledOnce());
});

it('labels future ungraded work from the server cutoff while due and zero-score work keep their meaning', async () => {
  const student: StudentDetail = { as_of: '2000-01-01', id: 'ada', name: 'Ada', grade_level: 4, section_id: 'class', section: 'Math', course_id: 'math', course: 'Math', average: 0, letter: 'F', gpa: 0, trend: null, attendance_rate: 100, homework_rate: 0, missing: 1, risk: 'at_risk', risk_reasons: [], absences: 0, tardies: 0, attendance: [{ day: '2000-01-01', status: 'present' }, { day: '2000-01-02', status: 'absent' }], notes: [], scores: [
    { assessment_id: 'future', title: 'Future work', kind: 'homework', due_date: '2000-01-02', max_points: 10, points: null, pct: null },
    { assessment_id: 'due', title: 'Due work', kind: 'homework', due_date: '2000-01-01', max_points: 10, points: null, pct: null },
    { assessment_id: 'zero', title: 'Scored zero', kind: 'quiz', due_date: '1999-12-31', max_points: 10, points: 0, pct: 0 },
    { assessment_id: 'early', title: 'Early recorded score', kind: 'quiz', due_date: '2000-01-02', max_points: 10, points: 10, pct: 100 },
  ] };
  vi.mocked(api).mockImplementation(async (path) => path.endsWith('/grade-history') ? { student_id: 'ada', active_section_id: 'class', sections: [] }
    : path.endsWith('/insight') ? { headline: 'Summary', strengths: [], concerns: [], actions: [], source: 'rules' } : student);
  setup(<Routes><Route path="/students/:id" element={<Student />} /></Routes>);
  const future = (await screen.findByText('Future work')).closest('tr')!;
  expect(within(future).getByText('not yet due')).toBeInTheDocument();
  expect(within(screen.getByText('Due work').closest('tr')!).getByText('missing')).toBeInTheDocument();
  expect(within(screen.getByText('Scored zero').closest('tr')!).getByText('0/10')).toBeInTheDocument();
  expect(within(screen.getByText('Early recorded score').closest('tr')!).getByText('10/10')).toBeInTheDocument();
  expect(screen.getByText('Not enough graded work to chart yet.')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Attendance across 1 recorded days: 1 present' })).toBeInTheDocument();
  expect(screen.queryByRole('group', { name: /Score trend across/ })).not.toBeInTheDocument();
});

function gradebook(day = '2026-09-30', points = 9, sectionId = 'class'): GradebookData {
  return { as_of: day, section: { id: sectionId, course_id: 'math', name: 'Math' }, assessments: [{ id: 'quiz', section_id: sectionId, title: 'Tomorrow quiz', kind: 'quiz', max_points: 10, due_date: '2026-10-01' }], rows: [{ student_id: 'ada', name: 'Ada', average: day < '2026-10-01' ? null : points * 10, letter: day < '2026-10-01' ? null : 'A-', points: { quiz: points } }] };
}
function gradebookReads() { return vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/gradebook')); }
async function advanceSchoolDay(client: QueryClient, day = '2026-10-01') {
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: day }); });
}
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }

it('refreshes the rendered grade once when the school day advances and preserves raw points', async () => {
  let day = '2026-09-30';
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: day } : gradebook(day)) as never);
  const { client } = setup(<Gradebook />);
  const row = (await screen.findByRole('link', { name: 'Ada' })).closest('tr')!;
  expect(row.querySelectorAll('td')[1]).toHaveTextContent('—');
  expect(screen.getByRole('textbox', { name: 'Ada, Tomorrow quiz' })).toHaveValue('9');
  day = '2026-10-01';
  await advanceSchoolDay(client);
  await waitFor(() => expect(gradebookReads()).toHaveLength(2));
  await waitFor(() => expect(row.querySelectorAll('td')[1]).toHaveTextContent('90% A-'));
  expect(screen.getByRole('textbox', { name: 'Ada, Tomorrow quiz' })).toHaveValue('9');
  expect(screen.getByText('Grades calculated through 2026-10-01')).toBeInTheDocument();
  await advanceSchoolDay(client);
  expect(gradebookReads()).toHaveLength(2);
});

it('labels a failed rollover with the old cutoff and retries explicitly without an automatic loop', async () => {
  let fail = true;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    const number = gradebookReads().length;
    if (number > 1 && fail) throw new Error('Rollover read unavailable');
    return gradebook(number > 1 ? '2026-10-01' : '2026-09-30') as never;
  });
  const { client, user } = setup(<Gradebook />);
  await screen.findByRole('link', { name: 'Ada' });
  await advanceSchoolDay(client);
  await screen.findByText('Rollover read unavailable');
  expect(screen.getByText('Grades calculated through 2026-09-30')).toBeInTheDocument();
  expect(screen.getByText(/Refresh failed. Use Retry/)).toHaveAttribute('role', 'status');
  expect(screen.queryByText('No students in this section')).not.toBeInTheDocument();
  await advanceSchoolDay(client);
  expect(gradebookReads()).toHaveLength(2);
  fail = false;
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByText('Grades calculated through 2026-10-01');
  expect(gradebookReads()).toHaveLength(3);
  expect(screen.getByRole('textbox', { name: 'Ada, Tomorrow quiz' })).toHaveValue('9');
});

it.each(['success', 'failure'] as const)('defers rollover during a pending score %s and coalesces the settlement refresh', async (outcome) => {
  const pending = deferred<GradebookData>();
  let day = '2026-09-30', points = 9;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: day } as never;
    if (options?.method === 'PUT') return pending.promise as never;
    const result = gradebook(day, points);
    if (points === 5 && day === '2026-10-01') result.rows[0].letter = 'F';
    return result as never;
  });
  const { client, user } = setup(<Gradebook />);
  const input = await screen.findByRole('textbox', { name: 'Ada, Tomorrow quiz' });
  await user.clear(input); await user.type(input, '5'); await user.tab();
  await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(1));
  day = '2026-10-01';
  await advanceSchoolDay(client);
  await screen.findByText(/Waiting for the latest school-day calculations/);
  expect(input).toHaveValue('5');
  expect(gradebookReads()).toHaveLength(1);
  await advanceSchoolDay(client);
  expect(gradebookReads()).toHaveLength(1);
  await act(async () => {
    if (outcome === 'success') { points = 5; pending.resolve(gradebook(day, points)); }
    else pending.reject(new Error('Score write failed'));
  });
  await screen.findByText('Grades calculated through 2026-10-01');
  await waitFor(() => expect(input).toHaveValue(outcome === 'success' ? '5' : '9'));
  expect(gradebookReads()).toHaveLength(2);
  expect(client.getQueryData<GradebookData>(['gradebook', 'class'])?.rows[0].average).toBe(outcome === 'success' ? 50 : 90);
});

it('attempts only once for an observed day even if a successful response still has an older cutoff', async () => {
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: '2026-09-30' } : gradebook()) as never);
  const { client } = setup(<Gradebook />);
  await screen.findByRole('link', { name: 'Ada' });
  await advanceSchoolDay(client);
  await waitFor(() => expect(gradebookReads()).toHaveLength(2));
  await waitFor(() => expect(client.getQueryState(['gradebook', 'class'])?.fetchStatus).toBe('idle'));
  await advanceSchoolDay(client);
  expect(gradebookReads()).toHaveLength(2);
  expect(screen.getByText('Grades calculated through 2026-09-30')).toBeInTheDocument();
  await advanceSchoolDay(client, '2026-10-02');
  await waitFor(() => expect(gradebookReads()).toHaveLength(3));
  await waitFor(() => expect(client.getQueryState(['gradebook', 'class'])?.fetchStatus).toBe('idle'));
  expect(gradebookReads()).toHaveLength(3);
});

it('aborts a superseded rollover read and ignores its late result after switching sections', async () => {
  const pending = deferred<GradebookData>();
  let oldReads = 0, signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (path === '/sections/class/gradebook') {
      if (++oldReads === 1) return gradebook() as never;
      signal = options?.signal;
      return pending.promise as never;
    }
    const other = gradebook('2026-10-01', 9, 'other');
    other.rows[0] = { ...other.rows[0], student_id: 'bea', name: 'Bea' };
    return other as never;
  });
  const { client, rerender } = setup(<Gradebook />);
  await screen.findByRole('link', { name: 'Ada' });
  await advanceSchoolDay(client);
  await waitFor(() => expect(oldReads).toBe(2));
  scope.section = { id: 'other', course_id: 'math', name: 'Other class' };
  rerender(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter><Gradebook /></MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  await screen.findByRole('link', { name: 'Bea' });
  expect(signal?.aborted).toBe(true);
  await act(async () => pending.resolve(gradebook('2026-09-30', 0)));
  expect(screen.queryByRole('link', { name: 'Ada' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Bea' })).toBeInTheDocument();
  expect(screen.getByText('Grades calculated through 2026-10-01')).toBeInTheDocument();
});

it('uses the response cutoff when the calendar is unavailable instead of inventing a school day', async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') throw new Error('Calendar unavailable');
    return gradebook('2000-01-01') as never;
  });
  setup(<Gradebook />);
  await screen.findByText('Grades calculated through 2000-01-01');
  expect(screen.getByText('Calendar unavailable')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '+ Assignment' })).toBeDisabled();
  expect(gradebookReads()).toHaveLength(1);
});

it('preserves an open assignment draft across rollover while a newly opened draft uses the new school day', async () => {
  let day = '2026-09-30';
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: day } : gradebook(day)) as never);
  const { user, client } = setup(<Gradebook />);
  await screen.findByRole('link', { name: 'Ada' });
  await user.click(screen.getByRole('button', { name: '+ Assignment' }));
  await user.type(screen.getByLabelText('Title'), 'Keep this draft');
  fireEvent.change(screen.getByLabelText('Due'), { target: { value: '2026-09-29' } });
  day = '2026-10-01';
  await advanceSchoolDay(client);
  await screen.findByText('Grades calculated through 2026-10-01');
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(screen.getByLabelText('Title')).toHaveValue('Keep this draft');
  expect(screen.getByLabelText('Due')).toHaveValue('2026-09-29');
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  await user.click(screen.getByRole('button', { name: '+ Assignment' }));
  expect(screen.getByLabelText('Due')).toHaveValue('2026-10-01');
});


it('revalidates an old cached Gradebook on reopening without changing its section key', async () => {
  vi.mocked(api).mockImplementation(async (path) => (path === '/calendar' ? { timezone: 'America/Los_Angeles', today: '2026-10-01' } : gradebook('2026-10-01')) as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(['gradebook', 'class'], gradebook());
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter><Gradebook /></MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  await screen.findByText('Grades calculated through 2026-10-01');
  expect(gradebookReads()).toHaveLength(1);
  expect(client.getQueryData<GradebookData>(['gradebook', 'class'])?.rows[0].average).toBe(90);
  expect(screen.getByRole('textbox', { name: 'Ada, Tomorrow quiz' })).toHaveValue('9');
});

it('clears a pending rollover at the authenticated-session boundary and rejects its late private result', async () => {
  const pending = deferred<GradebookData>();
  let reads = 0, signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { auth_required: true } as never;
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (++reads === 1) return gradebook() as never;
    signal = options?.signal;
    return pending.promise as never;
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><AuthGate onLogout={() => clearPrivateSession(client)}><ToastProvider><ConfirmProvider><MemoryRouter><Gradebook /></MemoryRouter></ConfirmProvider></ToastProvider></AuthGate></QueryClientProvider>);
  await screen.findByRole('link', { name: 'Ada' });
  await advanceSchoolDay(client);
  await waitFor(() => expect(reads).toBe(2));
  await act(async () => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
  expect(signal?.aborted).toBe(true);
  expect(screen.queryByRole('link', { name: 'Ada' })).not.toBeInTheDocument();
  await act(async () => pending.resolve(gradebook('2026-10-01')));
  expect(client.getQueryData(['gradebook', 'class'])).toBeUndefined();
  expect(screen.queryByText(/Grades calculated through/)).not.toBeInTheDocument();
});
