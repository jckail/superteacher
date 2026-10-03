import { QueryClient, QueryClientProvider, onlineManager } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import Gradebook from '../pages/Gradebook';
import { api } from '../api';
import { ToastProvider } from '../components/Toast';
import type { Gradebook as Data } from '../types';

vi.mock('../api', async original => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const { scope } = vi.hoisted(() => ({ scope: { ready: true, error: null as Error | null, section: { id: 'class', course_id: 'math', name: 'Math' } } }));
vi.mock('../scope', () => ({ useActiveSection: () => scope.ready ? scope.section : undefined, useScope: () => ({ isLoading: false, ready: scope.ready, error: scope.error }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
const data: Data = { as_of: '2026-10-02', section: { id: 'class', course_id: 'math', name: 'Math' }, assessments: [{ id: 'quiz', section_id: 'class', title: 'Quiz', kind: 'quiz', max_points: 10, due_date: '2026-10-02' }], rows: [
  { student_id: 'ada', name: 'Ada', average: null, letter: null, points: { quiz: null } },
  { student_id: 'ben', name: 'Ben', average: 0, letter: 'F', points: { quiz: 0 } },
] };
function deferred<T>() { let resolve!: (v: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  const content = () => <QueryClientProvider client={client}><ToastProvider><MemoryRouter><Gradebook /></MemoryRouter></ToastProvider></QueryClientProvider>;
  const view = render(content());
  return { client, refresh: () => view.rerender(content()) };
}
function builder() { return within(screen.getByRole('region', { name: 'Small-group builder' })); }
async function plan() {
  await screen.findByRole('checkbox', { name: 'Include group 1 in suggested plan' });
  fireEvent.click(builder().getByRole('checkbox', { name: 'Include group 1 in suggested plan' }));
  fireEvent.change(builder().getByLabelText('Available start time (school time)'), { target: { value: '09:00' } });
  fireEvent.click(builder().getByRole('button', { name: 'Suggest reteach slots' }));
  expect(builder().getByRole('region', { name: 'Suggested reteach plan' })).toHaveTextContent('09:00–09:15');
}
beforeEach(() => {
  scope.ready = true; scope.error = null; scope.section = { id: 'class', course_id: 'math', name: 'Math' };
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async path => (path === '/calendar' ? { timezone: 'UTC', today: data.as_of } : data) as never);
});
it('integrates due evidence below the original named score table without additional requests', async () => {
  setup(); await plan();
  expect(screen.getByRole('textbox', { name: 'Ben, Quiz' })).toHaveValue('0');
  expect(screen.getByRole('region', { name: 'Gradebook scores' })).not.toContainElement(screen.getByRole('region', { name: 'Small-group builder' }));
  const members = builder().getByRole('group', { name: 'Suggested group 1' });
  expect(members).toHaveTextContent('Ada · unscored'); expect(members).not.toHaveTextContent('Ben');
  expect(vi.mocked(api).mock.calls.map(([path]) => path).sort()).toEqual(['/calendar', '/sections/class/gradebook']);
});
it.each(['success', 'failure'] as const)('clears a reviewed plan during the actual optimistic score mutation (%s)', async outcome => {
  const pending = deferred<Data>(); let current = data;
  vi.mocked(api).mockImplementation((path, options) => {
    if (options?.method === 'PUT') return pending.promise as never;
    return Promise.resolve(path === '/calendar' ? { timezone: 'UTC', today: data.as_of } : current) as never;
  });
  setup(); await plan();
  const cell = screen.getByRole('textbox', { name: 'Ben, Quiz' });
  fireEvent.change(cell, { target: { value: '5' } }); fireEvent.blur(cell);
  await waitFor(() => expect(builder().queryByRole('checkbox')).not.toBeInTheDocument());
  expect(builder().queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
  await act(async () => {
    if (outcome === 'success') { current = { ...data, rows: data.rows.map(row => row.student_id === 'ben' ? { ...row, points: { quiz: 5 }, average: 50 } : row) }; pending.resolve(current); }
    else pending.reject(new Error('Synthetic score save failure'));
  });
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
  expect(builder().queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
});
it.each(['create', 'edit'] as const)('opening and cancelling an assignment %s dialog clears a reviewed plan', async kind => {
  setup(); await plan();
  fireEvent.click(screen.getByRole('button', { name: kind === 'create' ? '+ Assignment' : 'Edit Quiz' }));
  const dialog = await screen.findByRole('dialog');
  expect(builder().queryByRole('checkbox')).not.toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
  expect(builder().queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
});
it('clears plans for stale school-day evidence and metadata errors without reviving earlier selections', async () => {
  const { client, refresh } = setup(); await plan();
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'UTC', today: '2026-10-03' }); });
  await waitFor(() => expect(builder().queryByRole('checkbox')).not.toBeInTheDocument());
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'UTC', today: data.as_of }); });
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
  await plan(); scope.error = new Error('Metadata refresh unavailable'); refresh();
  expect(builder().queryByRole('checkbox')).not.toBeInTheDocument();
  scope.error = null; refresh();
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
});
it('hides cached actions while a real gradebook refresh is pending and failed', async () => {
  const { client } = setup(); await plan();
  const pending = deferred<Data>();
  vi.mocked(api).mockImplementation(path => (path.endsWith('/gradebook') ? pending.promise : Promise.resolve({ timezone: 'UTC', today: data.as_of })) as never);
  let done!: Promise<void>;
  act(() => { done = client.invalidateQueries({ queryKey: ['gradebook'] }); });
  await waitFor(() => expect(builder().queryByRole('checkbox')).not.toBeInTheDocument());
  await act(async () => { pending.reject(new Error('Synthetic read failure')); await done; });
  await screen.findByText('Synthetic read failure');
  expect(builder().queryByRole('checkbox')).not.toBeInTheDocument();
});

it.each(['gradebook', 'school-calendar'])('withholds cached groups while a real offline %s query is paused', async query => {
  const { client } = setup(); await plan();
  let done!: Promise<void>;
  try {
    onlineManager.setOnline(false);
    act(() => { done = client.invalidateQueries({ queryKey: [query] }); });
    await waitFor(() => expect(client.getQueryState(query === 'gradebook' ? [query, 'class'] : [query])?.fetchStatus).toBe('paused'));
    expect(builder().queryByRole('checkbox')).not.toBeInTheDocument();
  } finally {
    await act(async () => { onlineManager.setOnline(true); await done; });
  }
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
});
it('recomputes current evidence after a successful due-date metadata edit', async () => {
  let current = data;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (options?.method === 'PATCH') current = { ...data, assessments: data.assessments.map(a => ({ ...a, due_date: '2026-10-03' })) };
    return (path === '/calendar' ? { timezone: 'UTC', today: data.as_of } : current) as never;
  });
  setup(); await plan();
  fireEvent.click(screen.getByRole('button', { name: 'Edit Quiz' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByLabelText('Due'), { target: { value: '2026-10-03' } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save assignment' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await waitFor(() => expect(builder().getByRole('combobox', { name: 'Due assignment' })).toHaveTextContent('No due assignments'));
  expect(builder().queryByRole('checkbox')).not.toBeInTheDocument();
  expect(builder().queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
});

it('preserves a reviewed plan after a same-day calendar poll while withholding actions during the read', async () => {
  const { client } = setup(); await plan();
  const pending = deferred<{ timezone: string; today: string }>();
  vi.mocked(api).mockImplementation(path => (path === '/calendar' ? pending.promise : Promise.resolve(data)) as never);
  let done!: Promise<void>;
  act(() => { done = client.refetchQueries({ queryKey: ['school-calendar'] }); });
  await waitFor(() => expect(builder().queryByRole('checkbox')).not.toBeInTheDocument());
  await act(async () => { pending.resolve({ timezone: 'UTC', today: data.as_of }); await done; });
  await waitFor(() => expect(builder().getByRole('checkbox')).toBeChecked());
  expect(builder().getByRole('region', { name: 'Suggested reteach plan' })).toHaveTextContent('09:00–09:15');
});

it.each(['day', 'timezone'] as const)('clears a reviewed plan when a calendar poll changes the %s and does not revive it on restoration', async change => {
  const { client } = setup(); await plan();
  const calendar = { timezone: change === 'timezone' ? 'America/Los_Angeles' : 'UTC', today: change === 'day' ? '2026-10-03' : data.as_of };
  vi.mocked(api).mockImplementation(async path => (path === '/calendar' ? calendar : data) as never);
  await act(async () => { await client.refetchQueries({ queryKey: ['school-calendar'] }); });
  if (change === 'day') await waitFor(() => expect(builder().queryByRole('checkbox')).not.toBeInTheDocument());
  else await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
  vi.mocked(api).mockImplementation(async path => (path === '/calendar' ? { timezone: 'UTC', today: data.as_of } : data) as never);
  await act(async () => { await client.refetchQueries({ queryKey: ['school-calendar'] }); });
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
  expect(builder().queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
});
it('a failed calendar poll discards the review even after same-day recovery', async () => {
  const { client } = setup(); await plan();
  vi.mocked(api).mockImplementation(path => (path === '/calendar' ? Promise.reject(new Error('Calendar poll failed')) : Promise.resolve(data)) as never);
  await act(async () => { await client.refetchQueries({ queryKey: ['school-calendar'] }); });
  await screen.findByText('Calendar poll failed');
  expect(builder().queryByRole('checkbox')).not.toBeInTheDocument();
  vi.mocked(api).mockImplementation(async path => (path === '/calendar' ? { timezone: 'UTC', today: data.as_of } : data) as never);
  await act(async () => { await client.refetchQueries({ queryKey: ['school-calendar'] }); });
  await waitFor(() => expect(builder().getByRole('checkbox')).not.toBeChecked());
  expect(builder().queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
});
it('restores a focused group control after an unchanged poll without stealing a new outside focus', async () => {
  const { client } = setup(); await plan();
  async function poll(moveOutside: boolean) {
    const start = builder().getByLabelText('Available start time (school time)');
    start.focus(); expect(start).toHaveFocus();
    const pending = deferred<{ timezone: string; today: string }>();
    vi.mocked(api).mockImplementation(path => (path === '/calendar' ? pending.promise : Promise.resolve(data)) as never);
    let done!: Promise<void>;
    act(() => { done = client.refetchQueries({ queryKey: ['school-calendar'] }); });
    await waitFor(() => expect(builder().queryByRole('checkbox')).not.toBeInTheDocument());
    const outside = screen.getByRole('textbox', { name: 'Ben, Quiz' });
    if (moveOutside) outside.focus();
    await act(async () => { pending.resolve({ timezone: 'UTC', today: data.as_of }); await done; });
    await waitFor(() => expect(builder().getByRole('checkbox')).toBeChecked());
    if (moveOutside) expect(outside).toHaveFocus();
    else expect(builder().getByLabelText('Available start time (school time)')).toHaveFocus();
  }
  await poll(false); await poll(true);
});
