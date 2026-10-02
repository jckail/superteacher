import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import Reports from '../pages/Reports';
import { useRosterPage } from '../useRosterPage';
import { ApiError, UNAUTHORIZED_EVENT } from '../api';
import { AuthGate } from '../auth';
import type { ClassSummary, ParentUpdateOut, StudentPage, StudentSummary } from '../types';
const { request, scope } = vi.hoisted(() => ({ request: vi.fn(), scope: { ready: true, section: { id: 'p1', course_id: 'math', name: 'P1' } } }));
vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: request }));
vi.mock('../scope', () => ({ useActiveSection: () => scope.section, useScope: () => ({ ready: scope.ready, isLoading: false }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
vi.mock('../components/ScopeStatus', () => ({ default: () => null }));
const summary: ClassSummary = { as_of: '2026-10-01', section_id: 'p1', section: 'P1', course: 'Math', students: 3, unknown: 3, on_track: 0, watch: 0, at_risk: 0, average: null, distribution: { A: 0, B: 0, C: 0, D: 0, F: 0 }, assessments: [], attention: [], attendance: [], attendance_rate: null };
function student(id: string): StudentSummary { return { id, name: id, grade_level: 4, section_id: 'p1', section: 'P1', course_id: 'math', course: 'Math', average: null, letter: null, gpa: null, trend: null, attendance_rate: null, homework_rate: null, missing: 0, risk: 'unknown', risk_reasons: [] }; }
function page(ids: string[], next: string | null = null, matches = 3, scoped = 3): StudentPage { return { items: ids.map(student), next_cursor: next, as_of: '2026-10-01', total_matches: matches, total_scoped: scoped }; }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (value: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
const draft: ParentUpdateOut = { subject: 'Ada update', body: 'Private draft', source: 'template' };
function mount() { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); const view = render(<QueryClientProvider client={client}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>); return { client, user: userEvent.setup(), ...view }; }
function requests() { return request.mock.calls.filter(([path]) => path.startsWith('/students')); }
beforeEach(() => { request.mockReset(); scope.ready = true; scope.section = { id: 'p1', course_id: 'math', name: 'P1' }; request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : path.endsWith('/parent-update') ? Promise.resolve(draft) : Promise.resolve(page(['Ada', 'Bob'], 'private-name-cursor'))); });

it('fetches bounded pages with header cursors, pins one selected student and keeps edited draft through search', async () => {
  request.mockImplementation((path: string, options?: { rosterCursor?: string }) => {
    if (path.endsWith('/summary')) return Promise.resolve(summary);
    if (path.endsWith('/parent-update')) return Promise.resolve(draft);
    const q = new URL(path, 'https://example.test').searchParams.get('q');
    return Promise.resolve(q ? page([], null, 0) : options?.rosterCursor ? page(['Cara']) : page(['Ada', 'Bob'], 'private-name-cursor'));
  });
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  expect(requests()).toHaveLength(1);
  expect(requests()[0][0]).toContain('/students/page?');
  expect(new URL(requests()[0][0], 'https://example.test').searchParams.get('limit')).toBe('50');
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  const subject = await screen.findByLabelText('Subject');
  fireEvent.change(subject, { target: { value: 'My edit' } });
  await user.click(screen.getByRole('button', { name: 'Next students' }));
  await screen.findByRole('option', { name: 'Cara' });
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('Ada');
  expect(screen.getAllByRole('option').filter(o => o.getAttribute('value') === 'Ada')).toHaveLength(1);
  expect(requests()[1][1].rosterCursor).toBe('private-name-cursor');
  expect(requests()[1][0]).not.toContain('private-name-cursor');
  fireEvent.change(screen.getByLabelText('Search students'), { target: { value: '\uFEFF' } });
  await screen.findByText('No students match this search.');
  expect(new URL(requests().at(-1)![0], 'https://example.test').searchParams.get('q')).toBe('\uFEFF');
  expect(screen.getByLabelText('Subject')).toHaveValue('My edit');
  expect(screen.getByRole('button', { name: 'Regenerate' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Clear search' }));
  await screen.findByRole('option', { name: 'Bob' });
  expect(screen.getByLabelText('Subject')).toHaveValue('My edit');
  expect(requests().at(-1)![1].rosterCursor).toBeUndefined();
  expect(request.mock.calls.find(([p]) => p.endsWith('/parent-update'))?.[1].body).toEqual({ tone: 'warm', expected_section_id: 'p1' });
  client.clear();
});

it.each(['success', 'error'] as const)('rejects an old %s after a student ABA change and coalesces pending clicks', async (outcome) => {
  const pending = deferred<ParentUpdateOut>();
  request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : path.endsWith('/parent-update') ? pending.promise : Promise.resolve(page(['Ada', 'Bob'])));
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Generate draft' })); fireEvent.click(screen.getByRole('button', { name: /Drafting|Generate draft/ })); });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Bob');
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  expect(request.mock.calls.filter(([p]) => p.endsWith('/parent-update'))).toHaveLength(1);
  await act(async () => { if (outcome === 'success') pending.resolve(draft); else pending.reject(new ApiError(404, 'Old unavailable')); });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft' })).toBeEnabled());
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  expect(screen.queryByText(/Old unavailable/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('Ada');
  client.clear();
});

it('clears a selection on a matched invalidation once, while keeping the captured generation pending until settlement', async () => {
  const pending = deferred<ParentUpdateOut>();
  request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : path.endsWith('/parent-update') ? pending.promise : Promise.resolve(page(['Ada', 'Bob'])));
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await act(async () => { await client.invalidateQueries({ queryKey: ['unrelated'] }); });
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('Ada');
  await act(async () => { await client.invalidateQueries({ queryKey: ['students'] }); });
  await waitFor(() => expect(screen.getByLabelText('Student', { exact: true })).toHaveValue(''));
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Bob');
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  expect(requests()).toHaveLength(2);
  await act(async () => pending.resolve(draft));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft' })).toBeEnabled());
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  client.clear();
});

it('accepts a valid result after two synchronous clicks and rejects a tone ABA result', async () => {
  const first = deferred<ParentUpdateOut>(), second = deferred<ParentUpdateOut>();
  let writes = 0;
  request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : path.endsWith('/parent-update') ? (++writes === 1 ? first.promise : second.promise) : Promise.resolve(page(['Ada'])));
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  const button = screen.getByRole('button', { name: 'Generate draft' });
  act(() => { fireEvent.click(button); fireEvent.click(button); });
  expect(writes).toBe(1);
  await act(async () => first.resolve(draft));
  expect(await screen.findByLabelText('Subject')).toHaveValue('Ada update');
  await user.click(screen.getByRole('button', { name: 'Regenerate' }));
  await user.selectOptions(screen.getByLabelText('Tone'), 'neutral');
  await user.selectOptions(screen.getByLabelText('Tone'), 'warm');
  await act(async () => second.resolve(draft));
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  client.clear();
});

it.each(['retry', 'invalid cursor'] as const)('keeps a pinned selection on a read error and offers explicit %s recovery', async (kind) => {
  let fail = true;
  request.mockImplementation((path: string, options?: { rosterCursor?: string }) => {
    if (path.endsWith('/summary')) return Promise.resolve(summary);
    if (path.endsWith('/parent-update')) return Promise.resolve(draft);
    if (options?.rosterCursor && fail) return Promise.reject(new ApiError(kind === 'retry' ? 503 : 400, 'Student read failed'));
    return Promise.resolve(options?.rosterCursor ? page(['Cara']) : page(['Ada'], 'private-name-cursor'));
  });
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByLabelText('Subject');
  await user.click(screen.getByRole('button', { name: 'Next students' }));
  await screen.findByText(/Student read failed/);
  expect(screen.queryByText('Add students to this section to draft updates.')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('Ada');
  expect(screen.getByRole('button', { name: 'Regenerate' })).toBeEnabled();
  expect(requests()).toHaveLength(2);
  fail = false;
  await user.click(screen.getByRole('button', { name: kind === 'retry' ? 'Retry student list' : 'Restart student list' }));
  await screen.findByRole('option', { name: kind === 'retry' ? 'Cara' : 'Ada' });
  await waitFor(() => expect(requests()).toHaveLength(3));
  expect(requests()[2][1].rosterCursor).toBe(kind === 'retry' ? 'private-name-cursor' : undefined);
  expect(screen.getByLabelText('Subject')).toHaveValue('Ada update');
  client.clear();
});

it('clears private state at an unready scope boundary but keeps the write latch until the old request settles', async () => {
  const pending = deferred<ParentUpdateOut>();
  request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : path.endsWith('/parent-update') ? pending.promise : Promise.resolve(page(['Ada'])));
  const { user, client, rerender } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  scope.ready = false;
  rerender(<QueryClientProvider client={client}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>);
  expect(screen.queryByLabelText('Student', { exact: true })).not.toBeInTheDocument();
  expect(client.getQueryCache().findAll({ queryKey: ['students'] })).toHaveLength(0);
  scope.ready = true;
  rerender(<QueryClientProvider client={client}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  await act(async () => pending.resolve(draft));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft' })).toBeEnabled());
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  client.clear();
});

it('retains at most the active 50 rows plus one pinned snapshot and clears it when the section is genuinely empty', async () => {
  let empty = false;
  request.mockImplementation((path: string, options?: { rosterCursor?: string }) => path.endsWith('/summary') ? Promise.resolve(summary) : Promise.resolve(empty ? page([], null, 0, 0) : options?.rosterCursor ? page(Array.from({ length: 50 }, (_, i) => `Next${i}`), null, 101, 101) : page(['Ada', ...Array.from({ length: 49 }, (_, i) => `First${i}`)], 'private-name-cursor', 101, 101)));
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Next students' }));
  await screen.findByRole('option', { name: 'Next49' });
  expect(screen.getByLabelText('Student', { exact: true }).querySelectorAll('option')).toHaveLength(52);
  await waitFor(() => expect(client.getQueryCache().findAll({ queryKey: ['students'] })).toHaveLength(1));
  expect(JSON.stringify(client.getQueryCache().findAll({ queryKey: ['students'] }).map(q => q.queryKey))).not.toContain('private-name-cursor');
  empty = true;
  fireEvent.change(screen.getByLabelText('Search students'), { target: { value: 'gone' } });
  await screen.findByText('Add students to this section to draft updates.');
  await waitFor(() => expect(screen.getByLabelText('Student', { exact: true })).toHaveValue(''));
  expect(screen.getByRole('button', { name: 'Generate draft' })).toBeDisabled();
  client.clear();
});

it('ignores late clipboard completions after a draft edit and clears its owned timeout on unmount', async () => {
  const clipboard = deferred<void>();
  const { user, client, unmount } = mount();
  const write = vi.spyOn(navigator.clipboard, 'writeText').mockReturnValueOnce(clipboard.promise).mockResolvedValue(undefined);
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByLabelText('Subject');
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Edited' } });
  await act(async () => clipboard.resolve());
  expect(screen.queryByRole('button', { name: 'Copied ✓' })).not.toBeInTheDocument();
  const timer = vi.spyOn(globalThis, 'setTimeout');
  const clear = vi.spyOn(globalThis, 'clearTimeout');
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  await screen.findByRole('button', { name: 'Copied ✓' });
  const index = timer.mock.calls.findIndex(([, delay]) => delay === 2000);
  unmount();
  expect(clear).toHaveBeenCalledWith(timer.mock.results[index].value);
  write.mockRestore(); timer.mockRestore(); clear.mockRestore(); client.clear();
});

it('distinguishes an initial read failure from an empty section and retries without a legacy fetch', async () => {
  let fail = true;
  request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : fail ? Promise.reject(new Error('Read unavailable')) : Promise.resolve(page([], null, 0, 0)));
  const { user, client } = mount();
  await screen.findByText('Read unavailable');
  expect(screen.queryByText('Add students to this section to draft updates.')).not.toBeInTheDocument();
  expect(screen.queryByText('No students match this search.')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Generate draft' })).toBeDisabled();
  fail = false;
  await user.click(screen.getByRole('button', { name: 'Retry student list' }));
  await screen.findByText('Add students to this section to draft updates.');
  expect(requests()).toHaveLength(2);
  expect(requests().every(([path]) => path.startsWith('/students/page?'))).toBe(true);
  client.clear();
});

it('clears only the current unavailable selection on a generation404', async () => {
  request.mockImplementation((path: string) => path.endsWith('/summary') ? Promise.resolve(summary) : path.endsWith('/parent-update') ? Promise.reject(new ApiError(404, 'Student not found')) : Promise.resolve(page(['Ada', 'Bob'])));
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByText('Student not found');
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('');
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Bob');
  expect(screen.queryByText('Student not found')).not.toBeInTheDocument();
  client.clear();
});

it('shows clipboard feedback only for the latest copy and removes it on a failed repeat', async () => {
  const first = deferred<void>(), second = deferred<void>(), third = deferred<void>();
  const { user, client } = mount();
  const write = vi.spyOn(navigator.clipboard, 'writeText').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise);
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByLabelText('Subject');
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  await act(async () => second.resolve());
  await screen.findByRole('button', { name: 'Copied ✓' });
  await act(async () => first.resolve());
  expect(screen.getByRole('button', { name: 'Copied ✓' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Copied ✓' }));
  await act(async () => third.reject(new Error('Clipboard blocked')));
  expect(screen.queryByRole('button', { name: 'Copied ✓' })).not.toBeInTheDocument();
  write.mockRestore(); client.clear();
});

it('accepts the captured draft while only search changes and ignores superseded page responses', async () => {
  const read = deferred<StudentPage>(), generation = deferred<ParentUpdateOut>();
  request.mockImplementation((path: string) => {
    if (path.endsWith('/summary')) return Promise.resolve(summary);
    if (path.endsWith('/parent-update')) return generation.promise;
    const q = new URL(path, 'https://example.test').searchParams.get('q');
    return q === 'slow' ? read.promise : Promise.resolve(q ? page(['Bob'], null, 1) : page(['Ada']));
  });
  const { user, client } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  fireEvent.change(screen.getByLabelText('Search students'), { target: { value: 'slow' } });
  await waitFor(() => expect(requests().at(-1)?.[0]).toContain('q=slow'));
  const signal = requests().at(-1)![1].signal;
  fireEvent.change(screen.getByLabelText('Search students'), { target: { value: 'Bob' } });
  await screen.findByRole('option', { name: 'Bob' });
  expect(signal.aborted).toBe(true);
  await act(async () => { read.resolve(page(['Stale private name'])); generation.resolve(draft); });
  expect(screen.queryByRole('option', { name: 'Stale private name' })).not.toBeInTheDocument();
  expect(await screen.findByLabelText('Subject')).toHaveValue('Ada update');
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('Ada');
  client.clear();
});

it('auth teardown removes the picker, cursor cache and late private draft completion', async () => {
  const generation = deferred<ParentUpdateOut>();
  request.mockImplementation((path: string) => {
    if (path === '/auth/config') return Promise.resolve({ auth_mode: 'passcode' });
    if (path === '/auth/me') return Promise.resolve({ auth_required: true });
    if (path.endsWith('/summary')) return Promise.resolve(summary);
    if (path.endsWith('/parent-update')) return generation.promise;
    return Promise.resolve(page(['Ada']));
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const logout = () => client.clear();
  render(<QueryClientProvider client={client}><MemoryRouter><AuthGate onLogout={logout}><Reports /></AuthGate></MemoryRouter></QueryClientProvider>);
  const user = userEvent.setup();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  act(() => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
  expect(screen.queryByLabelText('Student', { exact: true })).not.toBeInTheDocument();
  expect(client.getQueryCache().findAll({ queryKey: ['students'] })).toHaveLength(0);
  await act(async () => generation.resolve(draft));
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  expect(screen.queryByText('Private draft')).not.toBeInTheDocument();
  client.clear();
});

it('clears selection across section ABA navigation and keeps the original generation latch', async () => {
  const pending = deferred<ParentUpdateOut>();
  request.mockImplementation((path: string) => {
    if (path.endsWith('/summary')) return Promise.resolve(summary);
    if (path.endsWith('/parent-update')) return pending.promise;
    const sectionId = new URL(path, 'https://example.test').searchParams.get('section_id') ?? 'p1';
    const response = page([sectionId === 'p1' ? 'Ada' : 'Cara']);
    response.items = response.items.map(s => ({ ...s, section_id: sectionId }));
    return Promise.resolve(response);
  });
  const { user, client, rerender } = mount();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  scope.section = { id: 'p2', course_id: 'math', name: 'P2' };
  rerender(<QueryClientProvider client={client}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('option', { name: 'Cara' });
  expect(screen.getByLabelText('Student', { exact: true })).toHaveValue('');
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Cara');
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  scope.section = { id: 'p1', course_id: 'math', name: 'P1' };
  rerender(<QueryClientProvider client={client}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>);
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByLabelText('Student', { exact: true }), 'Ada');
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  expect(request.mock.calls.filter(([path]) => path.endsWith('/parent-update'))).toHaveLength(1);
  await act(async () => pending.resolve(draft));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft' })).toBeEnabled());
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  client.clear();
});

it('notifies only once for a matched invalidation after the restart latch succeeds', async () => {
  const notice = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Probe() {
    const q = useRosterPage({ enabled: true, sectionId: 'p1', search: '', risk: '', sort: 'name', direction: 'asc' }, notice);
    return <><p>{q.data ? 'Page ready' : 'Page pending'}</p><button onClick={q.next}>Next probe</button><button onClick={q.previous}>Previous probe</button><button onClick={() => void q.retry()}>Retry probe</button></>;
  }
  request.mockImplementation((_path: string, options?: { rosterCursor?: string }) => Promise.resolve(page(['Ada'], options?.rosterCursor ? null : 'private-name-cursor')));
  render(<QueryClientProvider client={client}><Probe /></QueryClientProvider>);
  const user = userEvent.setup();
  await screen.findByText('Page ready');
  await user.click(screen.getByRole('button', { name: 'Next probe' }));
  await screen.findByText('Page ready');
  await user.click(screen.getByRole('button', { name: 'Previous probe' }));
  await screen.findByText('Page ready');
  await user.click(screen.getByRole('button', { name: 'Retry probe' }));
  await screen.findByText('Page ready');
  expect(notice).not.toHaveBeenCalled();
  const key = client.getQueryCache().findAll({ queryKey: ['students', 'page'] })[0].queryKey;
  // Two entries share the mounted session: the synchronous latch must coalesce their events.
  client.setQueryData([...key.slice(0, 4), 'other-snapshot', 9], page(['Other']));
  client.setQueryData(['students', { section: 'elsewhere' }], []);
  const before = requests().length;
  await act(async () => { await client.invalidateQueries({ queryKey: ['students'] }); });
  await screen.findByText('Page ready');
  expect(notice).toHaveBeenCalledTimes(1);
  expect(requests()).toHaveLength(before + 1);
  expect(requests().at(-1)![1].rosterCursor).toBeUndefined();
  client.clear();
});

it('selects distinct IDs with duplicate visible names and pins only the chosen ID across pages', async () => {
  request.mockImplementation((path: string, options?: { rosterCursor?: string }) => {
    if (path.endsWith('/summary')) return Promise.resolve(summary);
    if (path.endsWith('/parent-update')) return Promise.resolve(draft);
    const response = options?.rosterCursor ? page(['third']) : page(['first', 'second'], 'duplicate-name-cursor');
    response.items = response.items.map(s => ({ ...s, name: 'Alex Smith' }));
    return Promise.resolve(response);
  });
  const { user, client } = mount();
  const original = await screen.findAllByRole('option', { name: 'Alex Smith' });
  expect(original.map(option => option.getAttribute('value'))).toEqual(['first', 'second']);
  const select = screen.getByRole('combobox', { name: /^Student/ });
  await user.selectOptions(select, 'second');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByLabelText('Subject');
  const writes = () => request.mock.calls.filter(([path]) => path.endsWith('/parent-update'));
  expect(writes().map(([path]) => path)).toEqual(['/reports/students/second/parent-update']);
  expect(writes()[0][1].body).toEqual({ tone: 'warm', expected_section_id: 'p1' });
  await user.click(screen.getByRole('button', { name: 'Next students' }));
  await waitFor(() => expect(screen.getAllByRole('option', { name: 'Alex Smith' }).map(option => option.getAttribute('value'))).toEqual(['second', 'third']));
  expect(select).toHaveValue('second');
  expect(screen.getByLabelText('Subject')).toHaveValue('Ada update');
  await user.click(screen.getByRole('button', { name: 'Regenerate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Regenerate' })).toBeEnabled());
  expect(writes().map(([path]) => path)).toEqual(['/reports/students/second/parent-update', '/reports/students/second/parent-update']);
  await user.selectOptions(select, 'third');
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByLabelText('Subject');
  expect(writes().at(-1)![0]).toBe('/reports/students/third/parent-update');
  expect(select).toHaveValue('third');
  expect(screen.getAllByRole('option', { name: 'Alex Smith' })).toHaveLength(1);
  client.clear();
});
