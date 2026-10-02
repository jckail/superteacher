import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { ApiError, api, UNAUTHORIZED_EVENT } from '../api';
import { ToastProvider } from '../components/Toast';
import { ConfirmProvider } from '../components/Confirm';
import { AuthGate, clearPrivateSession, useAuth } from '../auth';
import Student from '../pages/Student';
import type { CourseOut, StudentDetail } from '../types';

vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const courses: CourseOut[] = [{ id: 'math', name: 'Math', sections: [{ id: 'a', name: 'Period A', course_id: 'math' }, { id: 'b', name: 'Period B', course_id: 'math' }] }];
function detail(day = '2026-10-01', section = 'a', id = 'ada'): StudentDetail {
  return { as_of: day, id, name: id === 'ada' ? 'Ada' : 'Ben', grade_level: 9, section_id: section, section: section === 'a' ? 'Period A' : 'Period B', course_id: 'math', course: 'Math', average: day < '2026-10-02' ? 80 : 90, letter: 'B', gpa: 3, trend: 10, attendance_rate: day < '2026-10-02' ? 100 : 50, homework_rate: day < '2026-10-02' ? 100 : 50, missing: day < '2026-10-02' ? 0 : 1, risk: 'on_track', risk_reasons: [], absences: day < '2026-10-02' ? 0 : 1, tardies: 0,
    notes: [{ id: 'note-1', body: 'Original note', created_at: '2026-10-01T12:00:00Z' }],
    attendance: [{ day: '2026-10-01', status: 'present' }, { day: '2026-10-02', status: 'absent' }],
    scores: [{ assessment_id: 'first', title: 'First quiz', kind: 'quiz', due_date: '2026-10-01', max_points: 10, points: 8, pct: 80 }, { assessment_id: 'second', title: 'Early recorded quiz', kind: 'quiz', due_date: '2026-10-02', max_points: 10, points: 10, pct: 100 }, { assessment_id: 'missing', title: 'Tomorrow homework', kind: 'homework', due_date: '2026-10-02', max_points: 10, points: null, pct: null }] };
}
function setup(client = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 0, staleTime: Infinity }, mutations: { retry: false } } })) {
  let navigate!: ReturnType<typeof useNavigate>;
  function Navigation() { navigate = useNavigate(); return null; }
  const view = render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}><Navigation /><Link to="/students/ada">Open Ada</Link><Link to="/students/ben">Open Ben</Link><Routes><Route path="/students/:id" element={<Student />} /><Route path="/roster" element={<h1>Roster</h1>} /></Routes></MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  return { ...view, client, user: userEvent.setup(), navigate: (path: string) => navigate(path) };
}
function reads(id = 'ada') { return vi.mocked(api).mock.calls.filter(([path, options]) => path === `/students/${id}` && !options?.method); }
function independent(path: string) {
  if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-10-01' };
  if (path === '/courses') return courses;
  if (path.endsWith('/insight')) return { headline: 'Independent insight through September', strengths: [], concerns: [], actions: [], source: 'rules' };
  if (path.endsWith('/grade-history')) return { student_id: path.split('/')[2], active_section_id: 'a', sections: [] };
  throw new Error(`Unexpected request ${path}`);
}
async function advance(client: QueryClient, day = '2026-10-02') { await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: day }); }); }
function stat(label: string) { return screen.getByText(label, { selector: '.label' }).closest('.stat')!; }
beforeEach(() => { vi.mocked(api).mockReset(); });

it('refreshes recorded metrics on a validated calendar advance without changing raw points or independent reads', async () => {
  let day = '2026-10-01';
  vi.mocked(api).mockImplementation(async (path) => (path === '/students/ada' ? detail(day) : independent(path)) as never);
  const { client } = setup();
  await screen.findByRole('heading', { name: /Ada/ });
  await screen.findByText('Independent insight through September');
  expect(stat('Average')).toHaveTextContent('80%');
  expect(within(screen.getByText('Tomorrow homework').closest('tr')!).getByText('not yet due')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Attendance across 1 recorded days: 1 present' })).toBeInTheDocument();
  const before = vi.mocked(api).mock.calls.filter(([path]) => path !== '/students/ada');
  day = '2026-10-02';
  await advance(client);
  await waitFor(() => expect(reads()).toHaveLength(2));
  await waitFor(() => expect(stat('Average')).toHaveTextContent('90%'));
  expect(stat('Attendance')).toHaveTextContent('50%');
  expect(stat('Homework')).toHaveTextContent('50%');
  expect(stat('Homework')).toHaveTextContent('1 missing');
  expect(within(screen.getByText('Tomorrow homework').closest('tr')!).getByText('missing')).toBeInTheDocument();
  expect(screen.getByRole('group', { name: 'Score trend across 2 assignments, latest 100%' })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Attendance across 2 recorded days: 1 present, 1 absent' })).toBeInTheDocument();
  expect(screen.getByText('Recorded metrics calculated through 2026-10-02')).toBeInTheDocument();
  expect(within(screen.getByText('Early recorded quiz', { selector: 'td' }).closest('tr')!).getByText('10/10')).toBeInTheDocument();
  expect(client.getQueryData<StudentDetail>(['student', 'ada'])?.scores).toEqual(detail().scores);
  expect(vi.mocked(api).mock.calls.filter(([path]) => path !== '/students/ada')).toEqual(before);
});

it.each(['profile', 'notes'] as const)('retains the actual %s editor DOM and drafts after an ordinary background read failure', async (editor) => {
  let fail = false;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/students/ada') { if (fail) throw new Error('Detail temporarily unavailable'); return detail() as never; }
    return independent(path) as never;
  });
  const { client, user } = setup();
  await screen.findByRole('heading', { name: /Ada/ });
  let input: HTMLElement;
  if (editor === 'profile') {
    await user.click(screen.getByRole('button', { name: 'Edit student' }));
    input = screen.getByLabelText('Name');
    await user.clear(input); await user.type(input, 'Ada draft');
    fireEvent.change(screen.getByLabelText('Grade level'), { target: { value: '10' } });
    await user.selectOptions(screen.getByLabelText('Section'), 'b');
  } else {
    await user.type(screen.getByRole('textbox', { name: 'New note' }), 'Keep new note');
    await user.click(screen.getByRole('button', { name: 'Edit note: Original note' }));
    input = screen.getByLabelText('Note');
    await user.clear(input); await user.type(input, 'Keep edit note');
  }
  fail = true;
  await act(async () => { await client.invalidateQueries({ queryKey: ['student', 'ada'], exact: true }); });
  await screen.findByText('Detail temporarily unavailable');
  if (editor === 'profile') {
    expect(screen.getByLabelText('Name')).toBe(input);
    expect(input).toHaveValue('Ada draft');
    expect(screen.getByLabelText('Grade level')).toHaveValue(10);
    expect(screen.getByLabelText('Section')).toHaveValue('b');
  } else {
    expect(screen.getByLabelText('Note')).toBe(input);
    expect(input).toHaveValue('Keep edit note');
    expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue('Keep new note');
  }
  expect(stat('Average')).toHaveTextContent('80%');
  expect(screen.getByText('Recorded metrics calculated through 2026-10-01')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  expect(vi.mocked(api).mock.calls.some(([, options]) => options?.method)).toBe(false);
});

function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
async function idle(client: QueryClient, id = 'ada') { await waitFor(() => expect(client.getQueryState(['student', id])?.fetchStatus).toBe('idle')); }
async function transfer(user: ReturnType<typeof userEvent.setup>, name = 'Ada transferred') {
  await user.click(screen.getByRole('button', { name: 'Edit student' }));
  await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), name);
  await user.selectOptions(screen.getByLabelText('Section'), 'b');
  await user.click(screen.getByRole('button', { name: 'Save student' }));
  await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(1));
}

it.each(['profile', 'notes'] as const)('keeps same-ID %s drafts and assignment filter through a successful day refresh', async (editor) => {
  let day = '2026-10-01';
  vi.mocked(api).mockImplementation(async (path) => (path === '/students/ada' ? detail(day) : independent(path)) as never);
  const { client, user } = setup();
  await screen.findByRole('heading', { name: /Ada/ });
  await user.click(within(screen.getByRole('group', { name: 'Filter by type' })).getByRole('button', { name: 'quiz' }));
  if (editor === 'profile') {
    await user.click(screen.getByRole('button', { name: 'Edit student' }));
    await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'Local name');
    fireEvent.change(screen.getByLabelText('Grade level'), { target: { value: '11' } });
    await user.selectOptions(screen.getByLabelText('Section'), 'b');
  } else {
    await user.type(screen.getByLabelText('New note'), 'New local note');
    await user.click(screen.getByRole('button', { name: 'Edit note: Original note' }));
    await user.clear(screen.getByLabelText('Note')); await user.type(screen.getByLabelText('Note'), 'Edited local note');
  }
  const draft = screen.getByLabelText(editor === 'profile' ? 'Name' : 'Note');
  day = '2026-10-02'; await advance(client);
  await screen.findByText('Recorded metrics calculated through 2026-10-02');
  expect(screen.getByLabelText(editor === 'profile' ? 'Name' : 'Note')).toBe(draft);
  expect(draft).toHaveValue(editor === 'profile' ? 'Local name' : 'Edited local note');
  if (editor === 'profile') { expect(screen.getByLabelText('Grade level')).toHaveValue(11); expect(screen.getByLabelText('Section')).toHaveValue('b'); }
  else expect(screen.getByLabelText('New note')).toHaveValue('New local note');
  expect(within(screen.getByRole('group', { name: 'Filter by type' })).getByRole('button', { name: 'quiz' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.queryByText('Tomorrow homework')).not.toBeInTheDocument();
});

it('bounds stale successful refreshes per ID/day, advances again later, and allows explicit recovery', async () => {
  let day = '2026-10-01';
  vi.mocked(api).mockImplementation(async (path) => (path === '/students/ada' ? detail(day) : independent(path)) as never);
  const { client, user } = setup(); await screen.findByRole('heading', { name: /Ada/ });
  await advance(client); await waitFor(() => expect(reads()).toHaveLength(2)); await idle(client);
  await advance(client); await idle(client); expect(reads()).toHaveLength(2);
  expect(screen.getByText('Recorded metrics calculated through 2026-10-01')).toBeInTheDocument();
  expect(screen.getByText(/Waiting for the latest school-day calculations/)).toBeInTheDocument();
  await advance(client, '2026-10-03'); await waitFor(() => expect(reads()).toHaveLength(3)); await idle(client);
  day = '2026-10-03'; await user.click(screen.getByRole('button', { name: 'Refresh recorded metrics' }));
  await screen.findByText('Recorded metrics calculated through 2026-10-03'); expect(reads()).toHaveLength(4);
});

it('uses one inherited retry after rollover failure, preserves cutoff and recovers explicitly without an automatic loop', async () => {
  let fail = true;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/students/ada') { if (reads().length > 1 && fail) throw new Error('Rollover unavailable'); return detail(reads().length > 1 ? '2026-10-02' : undefined) as never; }
    return independent(path) as never;
  });
  const { client, user } = setup(); await screen.findByRole('heading', { name: /Ada/ }); await advance(client);
  await screen.findByText('Rollover unavailable'); await idle(client);
  expect(reads()).toHaveLength(3); // Initial GET + rollover + inherited non404 retry.
  expect(screen.getByText(/Refresh failed. Use Retry/)).toBeInTheDocument();
  expect(screen.getByText('Recorded metrics calculated through 2026-10-01')).toBeInTheDocument();
  await advance(client); expect(reads()).toHaveLength(3);
  fail = false; await user.click(screen.getByRole('button', { name: 'Retry' }));
  await screen.findByText('Recorded metrics calculated through 2026-10-02'); expect(reads()).toHaveLength(4);
});

it.each(['covers', 'stale', 'failure'] as const)('coalesces an existing in-flight GET when its result %s the advanced day', async (outcome) => {
  const pending = deferred<StudentDetail>();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path !== '/students/ada') return independent(path) as never;
    if (reads().length === 2) return pending.promise as never;
    if (outcome === 'failure' && reads().length > 2) throw new Error('Existing GET failed');
    return detail(reads().length > 2 ? '2026-10-02' : undefined) as never;
  });
  const { client } = setup(); await screen.findByRole('heading', { name: /Ada/ });
  let background!: Promise<void>;
  await act(async () => { background = client.invalidateQueries({ queryKey: ['student', 'ada'], exact: true }); });
  await waitFor(() => expect(reads()).toHaveLength(2)); await advance(client); expect(reads()).toHaveLength(2);
  await act(async () => { if (outcome === 'failure') pending.reject(new Error('Existing GET failed')); else pending.resolve(detail(outcome === 'covers' ? '2026-10-02' : '2026-10-01')); await background; });
  await idle(client);
  if (outcome === 'failure') { await screen.findByText('Existing GET failed'); expect(reads()).toHaveLength(3); expect(stat('Average')).toHaveTextContent('80%'); }
  else { await screen.findByText('Recorded metrics calculated through 2026-10-02'); expect(reads()).toHaveLength(outcome === 'covers' ? 2 : 3); }
});

it('revalidates reopened old cache with the same detail key and does not recompute a newer cutoff backwards', async () => {
  vi.mocked(api).mockImplementation(async (path) => (path === '/students/ada' ? detail('2026-10-03') : independent(path)) as never);
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  client.setQueryData(['student', 'ada'], detail('2026-09-30'));
  const { user } = setup(client);
  await screen.findByText('Recorded metrics calculated through 2026-10-03'); expect(reads()).toHaveLength(1);
  await advance(client, '2026-10-02'); expect(reads()).toHaveLength(1);
  expect(stat('Average')).toHaveTextContent('90%');
  await user.click(screen.getByRole('button', { name: 'Refresh recorded metrics' })); await idle(client); expect(reads()).toHaveLength(2);
  expect(client.getQueryCache().findAll({ queryKey: ['student'] }).map((q) => q.queryKey)).toEqual([['student', 'ada']]);
});

it('retains empty response metrics and exposes independent calendar recovery without a browser date fallback', async () => {
  let calendarFails = true;
  const empty = { ...detail('2000-01-01'), scores: [], attendance: [], notes: [], average: null, letter: null, gpa: null, attendance_rate: null, homework_rate: null, missing: 0 };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') { if (calendarFails) throw new Error('School calendar unavailable'); return { timezone: 'America/Los_Angeles', today: '2000-01-01' } as never; }
    return (path === '/students/ada' ? empty : independent(path)) as never;
  });
  const { user } = setup(); await screen.findByText('Recorded metrics calculated through 2000-01-01');
  expect(screen.getByText('School calendar unavailable')).toBeInTheDocument();
  expect(screen.getByText('No attendance recorded yet.')).toBeInTheDocument();
  expect(screen.getByText(/No assignments yet/)).toBeInTheDocument(); expect(reads()).toHaveLength(1);
  calendarFails = false; await user.click(screen.getByRole('button', { name: 'Retry school calendar' }));
  await waitFor(() => expect(screen.queryByText('School calendar unavailable')).not.toBeInTheDocument()); expect(reads()).toHaveLength(1);
});

it.each(['cold', 'cached'] as const)('keeps typed404 fatal for %s detail and never retries it', async (mode) => {
  vi.mocked(api).mockImplementation(async (path) => { if (path === '/students/ada') throw new ApiError(404, 'Profile removed'); return independent(path) as never; });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 0, staleTime: Infinity } } });
  if (mode === 'cached') client.setQueryData(['student', 'ada'], detail());
  const { user } = setup(client);
  if (mode === 'cached') { await screen.findByRole('heading', { name: /Ada/ }); await user.click(screen.getByRole('button', { name: 'Edit student' })); await act(async () => { await client.invalidateQueries({ queryKey: ['student', 'ada'], exact: true }); }); }
  await screen.findByRole('heading', { name: 'Student not found' }); expect(reads()).toHaveLength(1);
  expect(screen.queryByLabelText('Name')).not.toBeInTheDocument(); expect(screen.queryByText(/Recorded metrics calculated through/)).not.toBeInTheDocument();
});

it('keeps a cold ordinary error retryable without inventing detail or a cutoff', async () => {
  let fail = true;
  vi.mocked(api).mockImplementation(async (path) => { if (path === '/students/ada') { if (fail) throw new Error('Offline'); return detail() as never; } return independent(path) as never; });
  const { user } = setup(); await screen.findByText('Offline'); expect(reads()).toHaveLength(2);
  expect(screen.queryByText(/Recorded metrics calculated through/)).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Edit student' })).not.toBeInTheDocument();
  fail = false; await user.click(screen.getByRole('button', { name: 'Retry' })); await screen.findByRole('heading', { name: /Ada/ });
});

it('does not treat cached ordinary not-found text as a typed404', async () => {
  vi.mocked(api).mockImplementation(async (path) => { if (path === '/students/ada') { if (reads().length > 1) throw new Error('Upstream not found temporarily'); return detail() as never; } return independent(path) as never; });
  const { client } = setup(); await screen.findByRole('heading', { name: /Ada/ });
  await act(async () => { await client.invalidateQueries({ queryKey: ['student', 'ada'], exact: true }); });
  await screen.findByText('Upstream not found temporarily'); expect(screen.getByRole('heading', { name: /Ada/ })).toBeInTheDocument(); expect(screen.queryByRole('heading', { name: 'Student not found' })).not.toBeInTheDocument();
});

it.each(['patch-first', 'get-first', 'get-failure'] as const)('preserves genuine transfer settlement with %s rollover ordering', async (order) => {
  const patch = deferred<StudentDetail>(), rollover = deferred<StudentDetail>(), settlement = deferred<StudentDetail>();
  let oldSignal: AbortSignal | undefined, serverSection = 'a';
  const updated = { ...detail('2026-10-02', 'b'), name: 'Ada transferred' };
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/students/ada' && options?.method === 'PATCH') return patch.promise as never;
    if (path === '/students/ada') {
      if (reads().length === 1) return detail() as never;
      if (reads().length === 2) { oldSignal = options?.signal; return rollover.promise as never; }
      if (order === 'get-failure' && serverSection === 'a') throw new Error('Rollover failed during transfer');
      return settlement.promise as never;
    }
    if (path.endsWith('/grade-history')) return { student_id: 'ada', active_section_id: serverSection, sections: [] } as never;
    return independent(path) as never;
  });
  const { client, user } = setup(); await screen.findByRole('heading', { name: /Ada/ }); await transfer(user); await advance(client);
  await waitFor(() => expect(reads()).toHaveLength(2));
  const draft = screen.getByLabelText('Name'); expect(draft).toHaveValue('Ada transferred'); expect(draft).toBeDisabled();
  expect(screen.getByLabelText('Section')).toHaveValue('b'); expect(screen.getByLabelText('Section')).toBeDisabled();
  const patchCalls = vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'PATCH');
  expect(patchCalls[0]).toEqual(['/students/ada', { method: 'PATCH', body: { name: 'Ada transferred', grade_level: 9, section_id: 'b' } }]);
  if (order !== 'patch-first') {
    await act(async () => { if (order === 'get-failure') rollover.reject(new Error('Rollover failed during transfer')); else rollover.resolve(detail('2026-10-02')); });
    await idle(client); expect(screen.getByLabelText('Name')).toBe(draft); expect(draft).toBeDisabled();
    if (order === 'get-failure') await screen.findByText('Rollover failed during transfer');
    else expect(client.getQueryData<StudentDetail>(['student', 'ada'])?.section_id).toBe('a');
  }
  serverSection = 'b'; await act(async () => patch.resolve(updated));
  await waitFor(() => expect(reads()).toHaveLength(order === 'get-failure' ? 4 : 3));
  if (order === 'patch-first') { expect(oldSignal?.aborted).toBe(true); await act(async () => rollover.resolve({ ...detail(), name: 'Late old Ada' })); }
  expect(screen.queryByRole('dialog', { name: 'Edit student' })).not.toBeInTheDocument();
  await act(async () => settlement.resolve(updated)); await idle(client);
  await screen.findByRole('heading', { name: /Ada transferred/ });
  expect(screen.getByText('Grade 9 · Math · Period B')).toBeInTheDocument();
  expect(client.getQueryData(['student', 'ada'])).toEqual(updated);
  await waitFor(() => expect(client.getQueryData(['grade-history', 'ada', 'b'])).toEqual({ student_id: 'ada', active_section_id: 'b', sections: [] }));
  expect(screen.queryByText(/The student’s section changed/)).not.toBeInTheDocument();
  expect(screen.getAllByText('Student updated')).toHaveLength(1);
  expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(1);
  await advance(client); expect(reads()).toHaveLength(order === 'get-failure' ? 4 : 3);
});

it.each(['success', 'failure'] as const)('keeps submitted transfer draft after failed PATCH following rollover %s', async (outcome) => {
  const patch = deferred<StudentDetail>(), rollover = deferred<StudentDetail>();
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/students/ada' && options?.method === 'PATCH') return patch.promise as never;
    if (path === '/students/ada') { if (reads().length === 1) return detail() as never; if (reads().length === 2) return rollover.promise as never; throw new Error('Rollover offline'); }
    return independent(path) as never;
  });
  const { client, user } = setup(); await screen.findByRole('heading', { name: /Ada/ }); await transfer(user); await advance(client);
  await waitFor(() => expect(reads()).toHaveLength(2));
  await act(async () => { if (outcome === 'success') rollover.resolve(detail('2026-10-02')); else rollover.reject(new Error('Rollover offline')); }); await idle(client);
  await act(async () => patch.reject(new Error('Transfer rejected'))); await screen.findByText('Transfer rejected');
  expect(screen.getByLabelText('Name')).toHaveValue('Ada transferred'); expect(screen.getByLabelText('Name')).toBeEnabled();
  expect(screen.getByLabelText('Section')).toHaveValue('b'); expect(screen.getByRole('dialog', { name: 'Edit student' })).toBeInTheDocument();
  expect(screen.queryByText('Student updated')).not.toBeInTheDocument();
  expect(client.getQueryData<StudentDetail>(['student', 'ada'])?.section_id).toBe('a');
  expect(reads()).toHaveLength(outcome === 'success' ? 2 : 3); expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(1);
});

it.each(['add', 'edit', 'delete'] as const)('keeps genuine %s-note settlement scoped when the write precedes the cancelled day GET', async (operation) => {
  await noteOrdering(operation, 'write-first');
});
it.each(['add', 'edit', 'delete'] as const)('keeps genuine %s-note settlement scoped when the day GET precedes the write', async (operation) => {
  await noteOrdering(operation, 'get-first');
});
async function noteOrdering(operation: 'add' | 'edit' | 'delete', order: 'write-first' | 'get-first') {
  const write = deferred<unknown>(), rollover = deferred<StudentDetail>(), settlement = deferred<StudentDetail>();
  let signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (options?.method) return write.promise as never;
    if (path === '/students/ada') { if (reads().length === 1) return detail() as never; if (reads().length === 2) { signal = options?.signal; return rollover.promise as never; } return settlement.promise as never; }
    return independent(path) as never;
  });
  const { client, user } = setup(); await screen.findByRole('heading', { name: /Ada/ }); await screen.findByText('Independent insight through September');
  if (operation === 'add') { await user.type(screen.getByLabelText('New note'), 'Captured addition'); await user.click(screen.getByRole('button', { name: 'Add' })); }
  else if (operation === 'edit') { await user.click(screen.getByRole('button', { name: 'Edit note: Original note' })); await user.clear(screen.getByLabelText('Note')); await user.type(screen.getByLabelText('Note'), 'Captured edit'); await user.click(screen.getByRole('button', { name: 'Save note' })); }
  else { await user.click(screen.getByRole('button', { name: 'Delete note: Original note' })); await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete note' })); }
  await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method)).toHaveLength(1));
  const expected = operation === 'add' ? ['/students/ada/notes', { method: 'POST', body: { body: 'Captured addition' } }] : operation === 'edit' ? ['/students/ada/notes/note-1', { method: 'PATCH', body: { body: 'Captured edit' } }] : ['/students/ada/notes/note-1', { method: 'DELETE' }];
  expect(vi.mocked(api).mock.calls.find(([, options]) => options?.method)).toEqual(expected);
  await advance(client); await waitFor(() => expect(reads()).toHaveLength(2));
  const insightBefore = vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/insight')).length; expect(insightBefore).toBe(1);
  if (order === 'get-first') { await act(async () => rollover.resolve(detail('2026-10-02'))); await idle(client); if (operation === 'edit') expect(screen.getByLabelText('Note')).toHaveValue('Captured edit'); }
  const committed = { ...detail('2026-10-02'), notes: operation === 'delete' ? [] : [{ id: operation === 'add' ? 'note-2' : 'note-1', body: operation === 'add' ? 'Captured addition' : 'Captured edit', created_at: '2026-10-01T12:00:00Z' }] };
  await act(async () => write.resolve(operation === 'delete' ? null : committed.notes[0])); await waitFor(() => expect(reads()).toHaveLength(3));
  if (order === 'write-first') { expect(signal?.aborted).toBe(true); await act(async () => rollover.resolve(detail())); }
  await act(async () => settlement.resolve(committed)); await idle(client);
  expect(client.getQueryData(['student', 'ada'])).toEqual(committed);
  expect(screen.queryByText('Original note', { selector: 'p' })).not.toBeInTheDocument();
  if (operation !== 'delete') expect(screen.getByText(operation === 'add' ? 'Captured addition' : 'Captured edit', { selector: 'p' })).toBeInTheDocument();
  expect(screen.getByLabelText('New note')).toHaveValue(''); expect(screen.queryByRole('dialog', { name: 'Edit private note' })).not.toBeInTheDocument();
  expect(screen.getAllByText(operation === 'add' ? 'Note added' : operation === 'edit' ? 'Note updated' : 'Note deleted')).toHaveLength(1);
  await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/insight'))).toHaveLength(insightBefore + 1));
  expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method)).toHaveLength(1); await advance(client); expect(reads()).toHaveLength(3);
}

it('preserves successful removal cache cleanup and never refetches the deleted detail or Insight', async () => {
  vi.mocked(api).mockImplementation(async (path, options) => (options?.method === 'DELETE' ? null : path === '/students/ada' ? detail() : independent(path)) as never);
  const { client, user } = setup(); await screen.findByRole('heading', { name: /Ada/ }); await screen.findByText('Independent insight through September');
  const count = reads().length, insightCount = vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/insight')).length;
  await user.click(screen.getByRole('button', { name: 'Remove student' })); await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove student' }));
  await screen.findByRole('heading', { name: 'Roster' }); await advance(client);
  expect(client.getQueryData(['student', 'ada'])).toBeUndefined(); expect(client.getQueryData(['insight', 'ada'])).toBeUndefined();
  expect(reads()).toHaveLength(count); expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/insight'))).toHaveLength(insightCount);
});

it('aborts superseded reads across actual A→B→A routing, resets the bounded attempt, and rejects late A', async () => {
  const old = deferred<StudentDetail>(), returned = deferred<StudentDetail>(); let signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/students/ada') { if (reads().length === 1) return detail() as never; if (reads().length === 2) { signal = options?.signal; return old.promise as never; } return returned.promise as never; }
    if (path === '/students/ben') return detail('2026-10-02', 'a', 'ben') as never;
    return independent(path) as never;
  });
  const { client, user, navigate } = setup(); await screen.findByRole('heading', { name: /Ada/ });
  await user.click(screen.getByRole('button', { name: 'Edit student' })); await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'Old A draft');
  await advance(client); await waitFor(() => expect(reads()).toHaveLength(2));
  await act(async () => navigate('/students/ben')); await screen.findByRole('heading', { name: /Ben/ }); expect(signal?.aborted).toBe(true);
  expect(screen.queryByLabelText('Name')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit student' })); expect(screen.getByLabelText('Name')).toHaveValue('Ben');
  await act(async () => navigate('/students/ada')); await waitFor(() => expect(reads()).toHaveLength(3));
  expect(screen.queryByLabelText('Name')).not.toBeInTheDocument();
  await act(async () => old.resolve({ ...detail(), name: 'Late old A' }));
  expect(client.getQueryData<StudentDetail>(['student', 'ada'])?.name).toBe('Ada');
  await act(async () => returned.resolve(detail('2026-10-02'))); await idle(client);
  expect(screen.getByRole('heading', { name: /Ada/ })).toBeInTheDocument(); expect(screen.queryByText('Late old A')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Edit student' })); expect(screen.getByLabelText('Name')).toHaveValue('Ada');
  expect(client.getQueryData(['student', 'ada'])).toEqual(detail('2026-10-02')); expect(client.getQueryData(['student', 'ben'])).toEqual(detail('2026-10-02', 'a', 'ben'));
});

it.each(['profile', 'note'] as const)('keeps B drafts/cache isolated from an unresolved A %s write completed after navigation', async (operation) => {
  const write = deferred<unknown>();
  vi.mocked(api).mockImplementation(async (path, options) => { if (options?.method) return write.promise as never; if (path === '/students/ada') return detail() as never; if (path === '/students/ben') return detail('2026-10-01', 'a', 'ben') as never; return independent(path) as never; });
  const { client, user, navigate } = setup(); await screen.findByRole('heading', { name: /Ada/ });
  if (operation === 'profile') await transfer(user);
  else { await user.type(screen.getByLabelText('New note'), 'A captured note'); await user.click(screen.getByRole('button', { name: 'Add' })); await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([, options]) => options?.method)).toHaveLength(1)); }
  await act(async () => navigate('/students/ben')); await screen.findByRole('heading', { name: /Ben/ });
  await user.click(screen.getByRole('button', { name: 'Edit student' })); const draft = screen.getByLabelText('Name'); await user.clear(draft); await user.type(draft, 'B local draft');
  const updatedA = { ...detail('2026-10-02', 'b'), name: 'Ada transferred' };
  await act(async () => write.resolve(operation === 'profile' ? updatedA : { id: 'note-new', body: 'A captured note', created_at: '2026-10-01T12:00:00Z' }));
  await waitFor(() => expect(client.getMutationCache().getAll().every((m) => m.state.status === 'success')).toBe(true));
  expect(screen.getByLabelText('Name')).toBe(draft); expect(draft).toHaveValue('B local draft'); expect(screen.getByRole('heading', { name: /Ben/ })).toBeInTheDocument();
  expect(client.getQueryData(['student', 'ben'])).toEqual(detail('2026-10-01', 'a', 'ben'));
  if (operation === 'profile') expect(client.getQueryData(['student', 'ada'])).toEqual(updatedA);
  expect(vi.mocked(api).mock.calls.find(([, options]) => options?.method)?.[0]).toBe(operation === 'profile' ? '/students/ada' : '/students/ada/notes');
});

it('keeps independent history mismatch rejection and previous-section policy after a day-only refresh', async () => {
  let day = '2026-10-01';
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/students/ada') return detail(day) as never;
    if (path.endsWith('/grade-history')) return { student_id: 'ada', active_section_id: 'wrong', sections: [{ section_id: 'previous', section: 'Old section', course_id: 'math', course: 'Math', scores: [{ assessment_id: 'old', title: 'Old raw work', kind: 'quiz', due_date: '2026-09-01', max_points: 10, points: 7, pct: 70 }] }] } as never;
    return independent(path) as never;
  });
  const { client } = setup(); await screen.findByText(/The student’s section changed/); day = '2026-10-02'; await advance(client); await screen.findByText('Recorded metrics calculated through 2026-10-02');
  expect(screen.getByText(/Previous-section scores are preserved here and do not affect/)).toBeInTheDocument(); expect(screen.queryByText('Old raw work')).not.toBeInTheDocument();
  expect(screen.getByText('Independent insight through September')).toBeInTheDocument(); expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/grade-history'))).toHaveLength(1); expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/insight'))).toHaveLength(1);
});

it('actual AuthGate expiry clears Student editors and private cache, aborts detail and rejects late reads', async () => {
  const read = deferred<StudentDetail>(); let signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/students/ada') { if (reads().length === 1) return detail() as never; signal = options?.signal; return read.promise as never; }
    return independent(path) as never;
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><AuthGate onLogout={() => clearPrivateSession(client)}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}><Routes><Route path="/students/:id" element={<Student />} /></Routes></MemoryRouter></ConfirmProvider></ToastProvider></AuthGate></QueryClientProvider>);
  const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: 'Edit student' })); await user.type(screen.getByLabelText('Name'), 'private draft');
  await advance(client); await waitFor(() => expect(reads()).toHaveLength(2)); await act(async () => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument(); expect(screen.queryByLabelText('Name')).not.toBeInTheDocument(); expect(signal?.aborted).toBe(true);
  expect(client.getQueryCache().getAll()).toHaveLength(0); await act(async () => read.resolve(detail('2026-10-02'))); expect(client.getQueryCache().getAll()).toHaveLength(0);
});

let Root: typeof import('../main')['Root'];
beforeAll(async () => { const element = document.createElement('div'); element.id = 'root'; document.body.append(element); try { ({ Root } = await import('../main')); } finally { element.remove(); } });

it.each(['expiry', 'logout'] as const)('actual Root %s/relogin isolates late Student mutation and aborted reads from the new client and preserves theme', async (boundary) => {
  const patch = deferred<StudentDetail>(), read = deferred<StudentDetail>(); const clients: QueryClient[] = []; let signal: AbortSignal | undefined, logout!: () => void;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/auth/login' || path === '/auth/logout') return {} as never;
    if (path === '/students/ada' && options?.method === 'PATCH') return patch.promise as never;
    if (path === '/students/ada') { if (reads().length === 2) { signal = options?.signal; return read.promise as never; } return detail(reads().length > 2 ? '2026-10-02' : undefined) as never; }
    return independent(path) as never;
  });
  function Probe() { const client = useQueryClient(); if (!clients.includes(client)) clients.push(client); logout = useAuth().logout; return <ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}><Routes><Route path="/students/:id" element={<Student />} /></Routes></MemoryRouter></ConfirmProvider></ToastProvider>; }
  localStorage.setItem('st-theme', 'dark'); render(<Root><Probe /></Root>); const user = userEvent.setup();
  await screen.findByRole('heading', { name: /Ada/ }); const old = clients[0]; await transfer(user); await advance(old); await waitFor(() => expect(reads()).toHaveLength(2));
  await act(async () => { if (boundary === 'expiry') window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)); else logout(); });
  await screen.findByRole('heading', { name: 'Sign in' }); expect(signal?.aborted).toBe(true); expect(screen.queryByLabelText('Name')).not.toBeInTheDocument(); expect(old.getQueryCache().getAll()).toHaveLength(0);
  await user.type(screen.getByLabelText('Passcode'), 'new-passcode'); await user.click(screen.getByRole('button', { name: 'Sign in' })); await screen.findByRole('heading', { name: /Ada/ });
  const current = clients[clients.length - 1]; expect(current).not.toBe(old); await user.click(screen.getByRole('button', { name: 'Edit student' })); await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'New session draft');
  await act(async () => { read.resolve({ ...detail(), name: 'Late private GET' }); patch.resolve({ ...detail('2026-10-02', 'b'), name: 'Late private PATCH' }); });
  expect(screen.getByLabelText('Name')).toHaveValue('New session draft'); expect(current.getQueryData<StudentDetail>(['student', 'ada'])?.name).toBe('Ada'); expect(current.getQueryData<StudentDetail>(['student', 'ada'])?.section_id).toBe('a'); expect(document.documentElement.dataset.theme).toBe('dark');
  expect(screen.queryByText('Late private PATCH', { selector: 'h1' })).not.toBeInTheDocument();
});
