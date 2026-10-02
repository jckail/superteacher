import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter, MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { ConfirmProvider } from '../components/Confirm';
import { ToastProvider } from '../components/Toast';
import Student from '../pages/Student';
import { useAuth } from '../auth';
import type { Insight, NoteOut, StudentDetail } from '../types';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function detail(id = 'ada'): StudentDetail {
  return { id, name: id === 'ada' ? 'Ada' : 'Ben', grade_level: 9, section_id: 'section-a', section: 'Period A', course_id: 'math', course: 'Math', as_of: '2026-10-02', average: 80, letter: 'B', gpa: 3, trend: 0, attendance_rate: 100, homework_rate: 100, missing: 0, risk: 'on_track', risk_reasons: [], absences: 0, tardies: 0, notes: [], attendance: [], scores: [] };
}
function insight(id: string): Insight { return { headline: `${id} independent insight`, strengths: [], concerns: [], actions: [], source: 'rules', model: null, generated_at: null }; }
function transport() {
  const write = deferred<NoteOut>();
  const settlement = deferred<StudentDetail>();
  let committed = false;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/students/ada/notes' && options?.method === 'POST') return write.promise as never;
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-10-02' } as never;
    const id = path.split('/')[2];
    if (path === `/students/${id}/insight`) return insight(id) as never;
    if (path === `/students/${id}/grade-history`) return { student_id: id, active_section_id: 'section-a', sections: [] } as never;
    if (path === `/students/${id}` && !options?.method) return (committed && id === 'ada' ? settlement.promise : detail(id)) as never;
    throw new Error(`Unexpected request ${path}`);
  });
  return { write, settlement, commit: () => { committed = true; } };
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  let navigate!: ReturnType<typeof useNavigate>;
  function Navigation() { navigate = useNavigate(); return null; }
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}><Navigation /><Routes><Route path="/students/:id" element={<Student />} /></Routes></MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  return { client, user: userEvent.setup(), navigate: async (path: string) => { await act(async () => navigate(path)); } };
}
function posts() { return vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'POST'); }
function detailReads(id = 'ada') { return vi.mocked(api).mock.calls.filter(([path, options]) => path === `/students/${id}` && !options?.method); }
async function ready(id = 'ada') {
  await screen.findByRole('heading', { name: new RegExp(id === 'ada' ? 'Ada' : 'Ben'), level: 1 });
  await screen.findByText(`${id} independent insight`);
}
const submittedRaw = '  Submitted observation  ';
const committedNote: NoteOut = { id: 'committed-note', body: 'Submitted observation', created_at: '2026-10-02T00:00:00Z' };
async function submit(user: ReturnType<typeof userEvent.setup>, raw = submittedRaw) {
  const input = screen.getByRole('textbox', { name: 'New note' });
  await user.type(input, raw);
  await user.click(screen.getByRole('button', { name: 'Add' }));
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0]).toEqual(['/students/ada/notes', { method: 'POST', body: { body: raw.trim() } }]);
  expect(input).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
  return input;
}
async function settle(fixture: ReturnType<typeof transport>, client: QueryClient) {
  fixture.commit();
  await act(async () => fixture.write.resolve(committedNote));
  await waitFor(() => expect(detailReads()).toHaveLength(2));
  expect(detailReads()[1][1]?.signal).toBeInstanceOf(AbortSignal);
  const committed = { ...detail(), notes: [committedNote] };
  await act(async () => fixture.settlement.resolve(committed));
  await screen.findByText(committedNote.body);
  await waitFor(() => expect(client.getQueryData(['student', 'ada'])).toEqual(committed));
  expect(posts()).toHaveLength(1);
  expect(screen.getAllByText('Note added')).toHaveLength(1);
}
beforeEach(() => { vi.mocked(api).mockReset(); });

it('clears an unchanged submitted draft after the real settlement GET displays the committed note', async () => {
  const fixture = transport(); const { user, client } = setup(); await ready();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const input = await submit(user);
  await settle(fixture, client);
  expect(screen.getByRole('textbox', { name: 'New note' })).toBe(input);
  expect(input).toHaveValue('');
  expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([['student', 'ada'], ['insight', 'ada']]);
});

it('preserves the latest raw draft typed during a pending POST after the real committed-note GET', async () => {
  const fixture = transport(); const { user, client } = setup(); await ready();
  const input = await submit(user);
  await user.clear(input); await user.type(input, '  Next observation  ');
  await settle(fixture, client);
  expect(screen.getByRole('textbox', { name: 'New note' })).toBe(input);
  expect(input).toHaveValue('  Next observation  ');
  expect(screen.getByRole('button', { name: 'Add' })).toBeEnabled();
});

it('preserves a draft edited away and back to identical raw text while the submitted POST is pending', async () => {
  const fixture = transport(); const { user, client } = setup(); await ready();
  const input = await submit(user);
  await user.clear(input); await user.type(input, 'Temporary replacement');
  await user.clear(input); await user.type(input, submittedRaw);
  await settle(fixture, client);
  expect(screen.getByRole('textbox', { name: 'New note' })).toBe(input);
  expect(input).toHaveValue(submittedRaw);
  expect(screen.getByRole('button', { name: 'Add' })).toBeEnabled();
});

it('keeps a latest whitespace-only raw draft and rejects another submission while pending', async () => {
  const fixture = transport(); const { user, client } = setup(); await ready();
  const input = await submit(user);
  await user.clear(input); await user.type(input, '   ');
  await user.keyboard('{Enter}');
  expect(posts()).toHaveLength(1);
  await settle(fixture, client);
  expect(input).toHaveValue('   ');
  expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
  await user.keyboard('{Enter}'); expect(posts()).toHaveLength(1);
});

it.each([false, true])('failed POST retains the latest raw draft (changed=%s) and retry submits it', async (changed) => {
  const fixture = transport(); const { user, client } = setup(); await ready();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const input = await submit(user);
  const latest = changed ? '  Retry observation  ' : submittedRaw;
  if (changed) { await user.clear(input); await user.type(input, latest); }
  await act(async () => fixture.write.reject(new Error('Note write unavailable')));
  await screen.findByText('Note write unavailable');
  expect(input).toHaveValue(latest); expect(invalidate).not.toHaveBeenCalled();
  expect(screen.queryByText('Note added')).not.toBeInTheDocument();
  expect(client.getQueryData(['student', 'ada'])).toEqual(detail());
  expect(detailReads()).toHaveLength(1);
  const retry = deferred<NoteOut>(); const ordinary = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) => options?.method === 'POST' ? retry.promise as never : ordinary(path, options));
  await user.click(screen.getByRole('button', { name: 'Add' }));
  await waitFor(() => expect(posts()).toHaveLength(2));
  expect(posts()[1]).toEqual(['/students/ada/notes', { method: 'POST', body: { body: latest.trim() } }]);
  const note = { ...committedNote, body: latest.trim() }; const result = { ...detail(), notes: [note] };
  fixture.commit();
  await act(async () => retry.resolve(note));
  await waitFor(() => expect(detailReads()).toHaveLength(2));
  await act(async () => fixture.settlement.resolve(result));
  await screen.findByText(note.body);
  expect(input).toHaveValue(''); expect(screen.getAllByText('Note added')).toHaveLength(1);
  expect(client.getQueryData(['student', 'ada'])).toEqual(result);
});

it('a deliberate second submit after success captures the preserved draft as a new request', async () => {
  const fixture = transport(); const { user, client } = setup(); await ready();
  const input = await submit(user);
  await user.clear(input); await user.type(input, '  Second observation  ');
  await settle(fixture, client);
  const second = deferred<NoteOut>(); const read = deferred<StudentDetail>();
  const ordinary = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (options?.method === 'POST') return second.promise as never;
    if (path === '/students/ada') return read.promise as never;
    return ordinary(path, options);
  });
  await user.click(screen.getByRole('button', { name: 'Add' }));
  await waitFor(() => expect(posts()).toHaveLength(2));
  expect(posts()[1]).toEqual(['/students/ada/notes', { method: 'POST', body: { body: 'Second observation' } }]);
  const secondNote = { ...committedNote, id: 'second-note', body: 'Second observation' };
  await act(async () => second.resolve(secondNote));
  await waitFor(() => expect(detailReads()).toHaveLength(3));
  const final = { ...detail(), notes: [committedNote, secondNote] };
  await act(async () => read.resolve(final));
  await screen.findByText(secondNote.body);
  expect(input).toHaveValue(''); expect(client.getQueryData(['student', 'ada'])).toEqual(final);
  expect(screen.getAllByText('Note added')).toHaveLength(2);
});

it.each(['success/read-first', 'success/write-first', 'error/read-first', 'error/write-first'])('same-ID day refresh preserves the pending draft through %s', async (scenario) => {
  const fixture = transport(); const dayRead = deferred<StudentDetail>();
  const ordinary = vi.mocked(api).getMockImplementation()!;
  let dayPending = false; let useDayRead = true; let daySignal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/students/ada' && !options?.method && dayPending && useDayRead) {
      daySignal = options?.signal; return dayRead.promise as never;
    }
    return ordinary(path, options);
  });
  const { user, client } = setup(); await ready(); const input = await submit(user);
  await user.clear(input); await user.type(input, '  Day draft retained  ');
  const initialCalls = vi.mocked(api).mock.calls.length;
  dayPending = true;
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-03' }); });
  await waitFor(() => expect(detailReads()).toHaveLength(2));
  expect(vi.mocked(api).mock.calls.slice(initialCalls).map(([path]) => path)).toEqual(['/students/ada']);
  expect(daySignal).toBeInstanceOf(AbortSignal);
  const error = scenario.startsWith('error');
  // Student owns its explicit retry option; return the same failure to its one retry.
  async function settleDay() {
    await act(async () => { if (error) dayRead.reject(new Error('Day detail unavailable')); else dayRead.resolve({ ...detail(), as_of: '2026-10-03' }); });
    if (error && scenario.endsWith('read-first')) await screen.findByText('Day detail unavailable', {}, { timeout: 4000 });
    else if (!error && scenario.endsWith('read-first')) await screen.findByText('Recorded metrics calculated through 2026-10-03');
  }
  if (scenario.endsWith('read-first')) {
    await settleDay();
    expect(screen.getByRole('textbox', { name: 'New note' })).toBe(input); expect(input).toHaveValue('  Day draft retained  ');
  }
  useDayRead = false; fixture.commit();
  const beforeWriteReads = detailReads().length;
  await act(async () => fixture.write.resolve(committedNote));
  await waitFor(() => expect(detailReads()).toHaveLength(beforeWriteReads + 1));
  if (scenario.endsWith('write-first')) {
    expect(daySignal?.aborted).toBe(true); await settleDay();
  }
  const final = { ...detail(), as_of: '2026-10-03', notes: [committedNote] };
  await act(async () => fixture.settlement.resolve(final));
  await screen.findByText(committedNote.body);
  expect(screen.getByRole('textbox', { name: 'New note' })).toBe(input); expect(input).toHaveValue('  Day draft retained  ');
  expect(client.getQueryData(['student', 'ada'])).toEqual(final);
  expect(posts()).toHaveLength(1); expect(screen.getAllByText('Note added')).toHaveLength(1);
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/students/ada/insight')).toHaveLength(2);
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/students/ada/grade-history')).toHaveLength(1);
});

it.each([false, true])('late A success preserves the actual replacement route draft (return to A=%s)', async (returnToA) => {
  const fixture = transport(); const { user, client, navigate } = setup(); await ready();
  const firstInput = await submit(user);
  await navigate('/students/ben'); await ready('ben');
  expect(screen.getByRole('textbox', { name: 'New note' })).not.toBe(firstInput);
  if (returnToA) { await navigate('/students/ada'); await ready(); }
  const replacement = screen.getByRole('textbox', { name: 'New note' });
  expect(replacement).toHaveValue(''); await user.type(replacement, '  Replacement lifecycle draft  ');
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  fixture.commit(); await act(async () => fixture.write.resolve(committedNote));
  await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(2));
  expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([['student', 'ada'], ['insight', 'ada']]);
  if (returnToA) {
    await waitFor(() => expect(detailReads()).toHaveLength(2));
    const final = { ...detail(), notes: [committedNote] };
    await act(async () => fixture.settlement.resolve(final)); await screen.findByText(committedNote.body);
    expect(client.getQueryData(['student', 'ada'])).toEqual(final);
  } else {
    expect(detailReads()).toHaveLength(1);
    expect(client.getQueryData(['student', 'ben'])).toEqual(detail('ben'));
    expect(client.getQueryData(['insight', 'ben'])).toEqual(insight('ben'));
  }
  expect(screen.getByRole('textbox', { name: 'New note' })).toBe(replacement);
  expect(replacement).toHaveValue('  Replacement lifecycle draft  '); expect(posts()).toHaveLength(1);
});

let Root: typeof import('../main')['Root'];
beforeAll(async () => {
  const element = document.createElement('div'); element.id = 'root'; document.body.append(element);
  try { ({ Root } = await import('../main')); } finally { element.remove(); }
});

it.each(['expiry', 'logout'] as const)('actual Root %s isolates a pending add from the next same-ID session and aborts its day read', async (boundary) => {
  const fixture = transport(); const ordinary = vi.mocked(api).getMockImplementation()!;
  const actualApi = (await vi.importActual<typeof import('../api')>('../api')).api;
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }));
  const oldDayRead = deferred<StudentDetail>(); let dayPending = false; let oldSignal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/session-probe') return actualApi(path, options);
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/auth/login' || path === '/auth/logout') return {} as never;
    if (dayPending && path === '/students/ada' && !options?.method) { oldSignal = options?.signal; return oldDayRead.promise as never; }
    return ordinary(path, options);
  });
  const clients: QueryClient[] = []; let logout!: () => void;
  function Probe() {
    const client = useQueryClient(); if (!clients.includes(client)) clients.push(client);
    logout = useAuth().logout;
    return <ToastProvider><ConfirmProvider><BrowserRouter><Routes><Route path="/students/:id" element={<Student />} /></Routes></BrowserRouter></ConfirmProvider></ToastProvider>;
  }
  const originalPath = window.location.pathname; window.history.replaceState(null, '', '/students/ada');
  const view = render(<Root><Probe /></Root>); const user = userEvent.setup(); await ready();
  const oldInput = await submit(user); const old = clients.at(-1)!;
  dayPending = true;
  await act(async () => { old.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-03' }); });
  await waitFor(() => expect(detailReads()).toHaveLength(2));
  await act(async () => { if (boundary === 'logout') logout(); else await api('/session-probe').catch(() => {}); });
  await screen.findByRole('heading', { name: 'Sign in' });
  expect(screen.queryByRole('textbox', { name: 'New note' })).not.toBeInTheDocument();
  expect(old.getQueryCache().getAll()).toHaveLength(0); expect(oldSignal?.aborted).toBe(true);
  dayPending = false;
  await user.type(screen.getByLabelText('Passcode'), 'new-passcode'); await user.click(screen.getByRole('button', { name: 'Sign in' })); await ready();
  const current = clients.at(-1)!; expect(current).not.toBe(old);
  const replacement = screen.getByRole('textbox', { name: 'New note' }); expect(replacement).not.toBe(oldInput);
  await user.type(replacement, '  New session draft  ');
  const invalidate = vi.spyOn(current, 'invalidateQueries'); const before = detailReads().length;
  await act(async () => { fixture.write.resolve(committedNote); oldDayRead.resolve({ ...detail(), as_of: '2026-10-03' }); });
  expect(invalidate).not.toHaveBeenCalled(); expect(detailReads()).toHaveLength(before);
  expect(current.getQueryData(['student', 'ada'])).toEqual(detail());
  expect(current.getQueryData(['insight', 'ada'])).toEqual(insight('ada'));
  expect(old.getQueryCache().getAll()).toHaveLength(0);
  expect(screen.getByRole('textbox', { name: 'New note' })).toBe(replacement); expect(replacement).toHaveValue('  New session draft  ');
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/students/ada/notes')).toEqual([['/students/ada/notes', { method: 'POST', body: { body: committedNote.body } }]]);
  if (boundary === 'expiry') expect(fetchMock).toHaveBeenCalledWith('/api/session-probe', expect.objectContaining({ method: 'GET' }));
  else expect(api).toHaveBeenCalledWith('/auth/logout', { method: 'POST' });
  view.unmount(); fetchMock.mockRestore(); window.history.replaceState(null, '', originalPath);
});
