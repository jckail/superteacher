import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter, MemoryRouter, Route, RouterProvider, Routes, createMemoryRouter, useBlocker, useLocation, useNavigate } from 'react-router-dom';
import { beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { ConfirmProvider } from '../components/Confirm';
import { ToastProvider } from '../components/Toast';
import Student from '../pages/Student';
import { useAuth } from '../auth';
vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
import type { CourseOut, Insight, StudentDetail } from '../types';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const courses: CourseOut[] = [{ id: 'math', name: 'Math', sections: [{ id: 'a', name: 'Period A', course_id: 'math' }, { id: 'b', name: 'Period B', course_id: 'math' }] }];
function detail(id: string): StudentDetail {
  return { id, name: id === 'ada' ? 'Ada' : 'Ben', grade_level: id === 'ada' ? 9 : 10, section_id: id === 'ada' ? 'a' : 'b', section: id === 'ada' ? 'Period A' : 'Period B', course_id: 'math', course: 'Math', as_of: '2026-10-02', average: id === 'ada' ? 80 : 90, letter: 'B', gpa: 3, trend: 0, attendance_rate: 100, homework_rate: 100, missing: 0, risk: 'on_track', risk_reasons: [], absences: 0, tardies: 0, notes: [], attendance: [{ day: '2026-10-02', status: 'present' }], scores: [{ assessment_id: `${id}-quiz`, title: `${id} quiz`, kind: 'quiz', due_date: '2026-10-02', max_points: 10, points: 8, pct: 80 }] };
}
function insight(id: string): Insight { return { headline: `${id} independent insight`, strengths: [], concerns: [], actions: [], source: 'rules', model: null, generated_at: null }; }
function transport(deletion = deferred<null>()) {
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (options?.method === 'DELETE') return deletion.promise as never;
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-10-02' } as never;
    if (path === '/courses') return courses as never;
    const id = path.split('/')[2];
    if (path === `/students/${id}/insight`) return insight(id) as never;
    if (path === `/students/${id}/grade-history`) return { student_id: id, active_section_id: id === 'ada' ? 'a' : 'b', sections: [] } as never;
    if (path === `/students/${id}`) return detail(id) as never;
    throw new Error(`Unexpected request ${path}`);
  });
  return deletion;
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  let navigate!: ReturnType<typeof useNavigate>;
  const locations: string[] = [];
  function Navigation() {
    navigate = useNavigate();
    const location = useLocation();
    if (locations.at(-1) !== location.pathname) locations.push(location.pathname);
    return <output aria-label="Current route">{location.pathname}</output>;
  }
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}><Navigation /><Routes><Route path="/students/:id" element={<Student />} /><Route path="/roster" element={<h1>Roster</h1>} /></Routes></MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  return { client, locations, user: userEvent.setup(), navigate: async (path: string) => { await act(async () => navigate(path)); } };
}
function deletes() { return vi.mocked(api).mock.calls.filter(([, options]) => options?.method === 'DELETE'); }
function reads(id: string) { return vi.mocked(api).mock.calls.filter(([path, options]) => !options?.method && (path === `/students/${id}` || path === `/students/${id}/insight`)); }
function detailReads(id: string) { return vi.mocked(api).mock.calls.filter(([path, options]) => path === `/students/${id}` && !options?.method); }
async function ready(id = 'ada', hidden = false) {
  await screen.findByRole('heading', { name: new RegExp(id === 'ada' ? 'Ada' : 'Ben'), level: 1, hidden });
  await screen.findByText(`${id} independent insight`);
}
async function openRemoval(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Remove student' }));
  const dialog = screen.getByRole('alertdialog', { name: 'Remove Ada?' });
  expect(dialog).toHaveTextContent('This permanently deletes the student and all of their scores, attendance and notes.');
  return dialog;
}
beforeEach(() => { vi.mocked(api).mockReset(); });

it('same lifecycle submits exactly A and removes its detail/Insight before invalidation and roster navigation', async () => {
  const deletion = transport();
  const { client, user, locations } = setup();
  await ready();
  const events: string[] = [];
  const remove = client.removeQueries.bind(client);
  vi.spyOn(client, 'removeQueries').mockImplementation((filters) => { events.push(`remove:${filters?.queryKey?.join(':')}`); return remove(filters); });
  const invalidate = client.invalidateQueries.bind(client);
  vi.spyOn(client, 'invalidateQueries').mockImplementation((...args) => { events.push('invalidate'); return invalidate(...args); });
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  expect(deletes()[0]).toEqual(['/students/ada', { method: 'DELETE' }]);
  const before = reads('ada').length;
  await act(async () => deletion.resolve(null));
  await screen.findByRole('heading', { name: 'Roster' });
  expect(events.slice(0, 3)).toEqual(['remove:student:ada', 'remove:insight:ada', 'invalidate']);
  expect(client.getQueryData(['student', 'ada'])).toBeUndefined();
  expect(client.getQueryData(['insight', 'ada'])).toBeUndefined();
  expect(reads('ada')).toHaveLength(before);
  expect(locations.filter((path) => path === '/roster')).toHaveLength(1);
});

it('does not GET the deleted student when the page stays mounted after DELETE', async () => {
  const deletion = transport();
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false }, mutations: { retry: false } } });
  function StayMounted() {
    useBlocker(true);
    return <Student />;
  }
  const router = createMemoryRouter([
    { path: '/students/:id', element: <StayMounted /> },
    { path: '/roster', element: <h1>Roster</h1> },
  ], { initialEntries: ['/students/ada'] });
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><RouterProvider router={router} /></ConfirmProvider></ToastProvider></QueryClientProvider>);
  const user = userEvent.setup();
  await ready();
  const before = detailReads('ada').length;
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  await act(async () => { deletion.resolve(null); });
  await screen.findByText('Student removed');
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(detailReads('ada')).toHaveLength(before);
  expect(client.getQueryData(['student', 'ada'])).toBeUndefined();
  expect(client.getQueryData(['insight', 'ada'])).toBeUndefined();
});

it('cancels an A confirmation after committed B navigation instead of deleting B', async () => {
  transport();
  const { client, user, navigate } = setup();
  await ready();
  const dialog = await openRemoval(user);
  await navigate('/students/ben');
  await ready('ben', true);
  expect(screen.getByRole('alertdialog', { name: 'Remove Ada?' })).toBe(dialog);
  expect(client.getQueryData(['student', 'ben'])).toEqual(detail('ben'));
  await user.click(within(dialog).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(deletes()).toHaveLength(0);
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/students/ben');
  expect(client.getQueryData(['student', 'ben'])).toEqual(detail('ben'));
  expect(client.getQueryData(['insight', 'ben'])).toEqual(insight('ben'));
});

it('late submitted A success removes only A caches and preserves B route and actual profile draft', async () => {
  const deletion = transport();
  const { client, user, navigate } = setup();
  await ready();
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  expect(deletes()[0][0]).toBe('/students/ada');
  await navigate('/students/ben');
  await ready('ben');
  await user.click(screen.getByRole('button', { name: 'Edit student' }));
  const name = screen.getByLabelText('Name');
  fireEvent.change(name, { target: { value: 'Ben retained draft' } });
  const section = screen.getByLabelText('Section');
  await user.selectOptions(section, 'a');
  const removed: unknown[] = [];
  const remove = client.removeQueries.bind(client);
  vi.spyOn(client, 'removeQueries').mockImplementation((filters) => { removed.push(filters?.queryKey); return remove(filters); });
  await act(async () => deletion.resolve(null));
  await waitFor(() => expect(removed).toHaveLength(2));
  expect(removed).toEqual([['student', 'ada'], ['insight', 'ada']]);
  expect(deletes().map(([path]) => path)).toEqual(['/students/ada']);
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/students/ben');
  expect(screen.getByLabelText('Name')).toBe(name);
  expect(name).toHaveValue('Ben retained draft');
  expect(screen.getByLabelText('Section')).toBe(section);
  expect(section).toHaveValue('a');
  expect(client.getQueryData(['student', 'ben'])).toEqual(detail('ben'));
  expect(client.getQueryData(['insight', 'ben'])).toEqual(insight('ben'));
});

it('an old confirmation remains cancelled after committed A to B to A; a fresh A confirmation works', async () => {
  const deletion = transport();
  const { client, user, navigate } = setup();
  await ready();
  const dialog = await openRemoval(user);
  await navigate('/students/ben'); await ready('ben', true);
  await navigate('/students/ada'); await ready('ada', true);
  await user.click(within(dialog).getByRole('button', { name: 'Remove student' }));
  expect(deletes()).toHaveLength(0);
  expect(client.getQueryData(['student', 'ada'])).toEqual(detail('ada'));
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/students/ada');
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  expect(deletes()[0][0]).toBe('/students/ada');
  await act(async () => deletion.resolve(null));
  await screen.findByRole('heading', { name: 'Roster' });
});

it('submitted A failure after B preserves both caches, B editor and route without another submission', async () => {
  const deletion = transport();
  const { client, user, navigate } = setup();
  await ready();
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  await navigate('/students/ben'); await ready('ben');
  await user.click(screen.getByRole('button', { name: 'Edit student' }));
  const name = screen.getByLabelText('Name');
  fireEvent.change(name, { target: { value: 'Ben failure draft' } });
  const remove = vi.spyOn(client, 'removeQueries');
  await act(async () => deletion.reject(new Error('Delete unavailable')));
  await screen.findByText('Couldn’t remove student: Delete unavailable');
  expect(remove).not.toHaveBeenCalled();
  for (const id of ['ada', 'ben']) {
    expect(client.getQueryData(['student', id])).toEqual(detail(id));
    expect(client.getQueryData(['insight', id])).toEqual(insight(id));
  }
  expect(deletes().map(([path]) => path)).toEqual(['/students/ada']);
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/students/ben');
  expect(screen.getByLabelText('Name')).toBe(name); expect(name).toHaveValue('Ben failure draft');
});

it.each(['read-first', 'delete-first'] as const)('a pre-delete day read cannot resurrect A after %s settlement or disturb B', async (order) => {
  const deletion = transport(), read = deferred<StudentDetail>();
  const ordinary = vi.mocked(api).getMockImplementation()!;
  let pending = false;
  let signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (pending && path === '/students/ada' && !options?.method) { signal = options?.signal; return read.promise as never; }
    return ordinary(path, options);
  });
  const { client, user, navigate } = setup();
  await ready();
  pending = true;
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-03' }); });
  await waitFor(() => expect(reads('ada').filter(([path]) => path === '/students/ada')).toHaveLength(2));
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  await navigate('/students/ben'); await ready('ben');
  await user.click(screen.getByRole('button', { name: 'Edit student' }));
  const name = screen.getByLabelText('Name'); fireEvent.change(name, { target: { value: 'Ben day draft' } });
  const before = reads('ada').length;
  if (order === 'read-first') await act(async () => read.resolve({ ...detail('ada'), as_of: '2026-10-03' }));
  await act(async () => deletion.resolve(null));
  await waitFor(() => expect(client.getQueryData(['student', 'ada'])).toBeUndefined());
  if (order === 'delete-first') await act(async () => read.resolve({ ...detail('ada'), as_of: '2026-10-03' }));
  expect(signal?.aborted).toBe(true);
  expect(client.getQueryData(['student', 'ada'])).toBeUndefined();
  expect(client.getQueryData(['insight', 'ada'])).toBeUndefined();
  expect(reads('ada')).toHaveLength(before);
  expect(deletes().map(([path]) => path)).toEqual(['/students/ada']);
  expect(client.getQueryData(['student', 'ben'])).toEqual(detail('ben'));
  expect(client.getQueryData(['insight', 'ben'])).toEqual(insight('ben'));
  expect(screen.getByLabelText('Current route')).toHaveTextContent('/students/ben');
  expect(screen.getByLabelText('Name')).toBe(name); expect(name).toHaveValue('Ben day draft');
});

let Root: typeof import('../main')['Root'];
beforeAll(async () => {
  const element = document.createElement('div'); element.id = 'root'; document.body.append(element);
  try { ({ Root } = await import('../main')); } finally { element.remove(); }
});

it.each(['expiry', 'logout'] as const)('actual Root %s cancels a pre-submit confirmation and isolates a submitted old DELETE from the next client', async (boundary) => {
  const deletion = transport();
  const ordinary = vi.mocked(api).getMockImplementation()!;
  const actualApi = (await vi.importActual<typeof import('../api')>('../api')).api;
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }));
  let sessionId = 'ada';
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/session-probe') return actualApi(path, options);
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/auth/login' || path === '/auth/logout') return {} as never;
    return ordinary(path, options);
  });
  const clients: QueryClient[] = [];
  let logout!: () => void;
  function Probe() {
    const client = useQueryClient(); if (!clients.includes(client)) clients.push(client);
    logout = useAuth().logout;
    return <ToastProvider><BrowserRouter><Routes><Route path="/students/:id" element={<Student />} /><Route path="/roster" element={<h1>Roster</h1>} /></Routes></BrowserRouter></ToastProvider>;
  }
  // Keep the actual global provider above Root so a pending promise can settle after actual AuthGate teardown.
  const originalPath = window.location.pathname;
  window.history.replaceState(null, '', '/students/ada');
  const view = render(<ConfirmProvider><Root><Probe /></Root></ConfirmProvider>);
  const user = userEvent.setup(); await ready();
  const oldDialog = await openRemoval(user);
  async function expire() {
    await act(async () => { if (boundary === 'logout') logout(); else await api('/session-probe').catch(() => {}); });
    await screen.findByRole('heading', { name: 'Sign in', hidden: true });
  }
  async function login() {
    await user.type(screen.getByLabelText('Passcode'), 'new-passcode');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    await ready(sessionId);
  }
  await expire();
  await user.click(within(oldDialog).getByRole('button', { name: 'Remove student' }));
  expect(deletes()).toHaveLength(0);
  expect(clients[0].getQueryCache().getAll()).toHaveLength(0);
  await login();
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  expect(deletes()[0][0]).toBe('/students/ada');
  const old = clients.at(-1)!;
  sessionId = 'ben'; await expire(); window.history.replaceState(null, '', '/students/ben'); await login();
  const current = clients.at(-1)!; expect(current).not.toBe(old);
  await user.click(screen.getByRole('button', { name: 'Edit student' }));
  const name = screen.getByLabelText('Name'); fireEvent.change(name, { target: { value: 'New session Ben draft' } });
  const remove = vi.spyOn(current, 'removeQueries');
  const invalidate = vi.spyOn(current, 'invalidateQueries');
  const currentA = { ...detail('ada'), name: 'New session A cache' };
  current.setQueryData(['student', 'ada'], currentA); current.setQueryData(['insight', 'ada'], insight('ada'));
  await act(async () => deletion.resolve(null));
  expect(remove).not.toHaveBeenCalled(); expect(invalidate).not.toHaveBeenCalled();
  expect(current.getQueryData(['student', 'ada'])).toEqual(currentA);
  expect(current.getQueryData(['insight', 'ada'])).toEqual(insight('ada'));
  expect(current.getQueryData(['student', 'ben'])).toEqual(detail('ben'));
  expect(current.getQueryData(['insight', 'ben'])).toEqual(insight('ben'));
  expect(screen.getByLabelText('Name')).toBe(name); expect(name).toHaveValue('New session Ben draft');
  expect(screen.queryByRole('heading', { name: 'Roster' })).not.toBeInTheDocument();
  expect(window.location.pathname).toBe('/students/ben');
  expect(deletes().map(([path]) => path)).toEqual(['/students/ada']);
  expect(old.getQueryData(['student', 'ada'])).toBeUndefined();
  if (boundary === 'expiry') expect(fetchMock).toHaveBeenCalledWith('/api/session-probe', expect.objectContaining({ method: 'GET' }));
  view.unmount(); fetchMock.mockRestore(); window.history.replaceState(null, '', originalPath);
});

it.each(['read-first', 'delete-first'] as const)('same-A pending freshness GET settles %s without deleted detail/Insight resurrection or replacement reads', async (order) => {
  const deletion = transport(), read = deferred<StudentDetail>();
  const ordinary = vi.mocked(api).getMockImplementation()!;
  let pending = false;
  let signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (pending && path === '/students/ada' && !options?.method) { signal = options?.signal; return read.promise as never; }
    return ordinary(path, options);
  });
  const { client, user } = setup(); await ready();
  pending = true;
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-03' }); });
  await waitFor(() => expect(reads('ada').filter(([path]) => path === '/students/ada')).toHaveLength(2));
  await user.click(within(await openRemoval(user)).getByRole('button', { name: 'Remove student' }));
  await waitFor(() => expect(deletes()).toHaveLength(1));
  const before = reads('ada').length;
  if (order === 'read-first') {
    await act(async () => read.resolve({ ...detail('ada'), as_of: '2026-10-03' }));
    await screen.findByText('Recorded metrics calculated through 2026-10-03');
  }
  await act(async () => deletion.resolve(null));
  await screen.findByRole('heading', { name: 'Roster' });
  if (order === 'delete-first') { expect(signal?.aborted).toBe(true); await act(async () => read.resolve({ ...detail('ada'), as_of: '2026-10-03' })); }
  expect(client.getQueryData(['student', 'ada'])).toBeUndefined();
  expect(client.getQueryData(['insight', 'ada'])).toBeUndefined();
  expect(reads('ada')).toHaveLength(before);
  expect(deletes().map(([path]) => path)).toEqual(['/students/ada']);
});
