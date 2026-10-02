import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { useAuth } from '../auth';
import userEvent from '@testing-library/user-event';
import Student, { Insight } from '../pages/Student';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ToastProvider } from '../components/Toast';
import { ConfirmProvider } from '../components/Confirm';
import type { Insight as InsightData, StudentDetail } from '../types';

vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
function payload(as_of = '2026-10-01') {
  return { as_of, headline: 'Recorded advice', strengths: [], concerns: [], actions: [], source: 'ai' as const, model: 'test', generated_at: '2026-10-01T15:23:00Z' };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false } } });
  const page = (id: string) => <QueryClientProvider client={client}><Insight id={id} /></QueryClientProvider>;
  const view = render(page('ada'));
  return { client, change: (id: string) => view.rerender(page(id)) };
}
const reads = () => vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/insight'));
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => path === '/calendar'
    ? { timezone: 'America/Los_Angeles', today: '2026-10-01' } as never : payload() as never);
});
it('shows independent cutoff and AI timestamp without refreshing on school-day advance', async () => {
  const { client } = setup();
  expect(await screen.findByText('Insight calculations through 2026-10-01')).toBeInTheDocument();
  expect(screen.getByText(/AI generated at/).querySelector('time')).toHaveAttribute('datetime', '2026-10-01T15:23:00Z');
  expect(screen.getByText(/AI generated at/)).toHaveTextContent(new Date('2026-10-01T15:23:00Z').toLocaleString());
  expect(screen.getByText(/Records may have changed since this insight/)).toBeInTheDocument();
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-02' }); });
  expect(await screen.findByRole('status')).toHaveTextContent('earlier school day');
  expect(reads()).toHaveLength(1);
  expect(screen.getByText(/may use your AI allowance/)).toBeInTheDocument();
});
it('makes one deferred explicit refresh and preserves old provenance while fetching', async () => {
  const response = deferred<InsightData>();
  setup(); await screen.findByText('Recorded advice');
  vi.mocked(api).mockImplementation(async () => response.promise as never);
  const button = screen.getByRole('button', { name: 'Refresh insight' });
  act(() => { fireEvent.click(button); fireEvent.click(button); });
  await waitFor(() => expect(reads()).toHaveLength(2));
  expect(button).toBeDisabled();
  expect(screen.getByText('Insight calculations through 2026-10-01')).toBeInTheDocument();
  await act(async () => response.resolve({ ...payload('2026-10-02'), headline: 'Updated advice', generated_at: '2026-10-02T12:00:00Z' }));
  expect(await screen.findByText('Updated advice')).toBeInTheDocument();
  expect(screen.getByText('Insight calculations through 2026-10-02')).toBeInTheDocument();
  expect(button).toBeEnabled(); expect(reads()).toHaveLength(2);
});
it('retains old content after quota failure and offers only the guarded action', async () => {
  setup(); await screen.findByText('Recorded advice');
  vi.mocked(api).mockRejectedValue(new Error('AI allowance exhausted'));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh insight' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('AI allowance exhausted');
  expect(screen.getByText('Recorded advice')).toBeInTheDocument();
  expect(screen.getByText('Insight calculations through 2026-10-01')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  vi.mocked(api).mockResolvedValue(payload()); fireEvent.click(screen.getByRole('button', { name: 'Refresh insight' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument()); expect(reads()).toHaveLength(3);
});
it('shows rule cutoff without AI timestamp and treats old cached cutoff as unknown', async () => {
  const { client } = setup(); await screen.findByText('Recorded advice');
  await act(async () => { client.setQueryData(['insight', 'ada'], { ...payload(), source: 'rules', model: null, generated_at: null }); });
  expect(screen.getByText('Insight calculations through 2026-10-01')).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText(/AI generated at/)).not.toBeInTheDocument());
  const old: Partial<ReturnType<typeof payload>> = payload(); delete old.as_of;
  await act(async () => { client.setQueryData(['insight', 'ada'], old); });
  expect(await screen.findByText('Insight calculation cutoff unavailable.')).toBeInTheDocument();
  expect(screen.queryByText('Insight calculations through 2026-10-01')).not.toBeInTheDocument(); expect(reads()).toHaveLength(1);
});
it('does not infer current freshness from a failed calendar', async () => {
  vi.mocked(api).mockImplementation(async (path) => { if (path === '/calendar') throw new Error('Calendar unavailable'); return payload() as never; });
  setup(); await screen.findByText('Recorded advice');
  expect(await screen.findByText('School-day freshness unavailable.')).toBeInTheDocument(); expect(reads()).toHaveLength(1);
});
it('aborts old student refresh and isolates new identity and ABA content', async () => {
  const pending = deferred<InsightData>(); let oldSignal!: AbortSignal;
  const { change } = setup(); await screen.findByText('Recorded advice');
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/students/ada/insight') { oldSignal = options!.signal!; return pending.promise as never; }
    return { ...payload('2026-10-02'), headline: 'Ben advice' } as never;
  });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh insight' })); await waitFor(() => expect(reads()).toHaveLength(2));
  change('ben'); expect(await screen.findByText('Ben advice')).toBeInTheDocument(); expect(oldSignal.aborted).toBe(true);
  await act(async () => pending.resolve({ ...payload(), headline: 'Obsolete completion' }));
  expect(screen.queryByText('Obsolete completion')).not.toBeInTheDocument();
  change('ada'); expect(await screen.findByText('Recorded advice')).toBeInTheDocument();
  expect(screen.queryByText('Ben advice')).not.toBeInTheDocument(); expect(screen.getByRole('button', { name: 'Refresh insight' })).toBeEnabled();
});


it('shares the full Student calendar read and keeps Insight independent of detail day refresh', async () => {
  let day = '2026-10-01';
  const detail = (): StudentDetail => ({ as_of: day, id: 'ada', name: 'Ada', grade_level: 9, section_id: 'class', section: 'Math', course_id: 'math', course: 'Math', average: 80, letter: 'B', gpa: 3, trend: 0, attendance_rate: 100, homework_rate: 100, missing: 0, risk: 'on_track', risk_reasons: [], scores: [], attendance: [], absences: 0, tardies: 0, notes: [] });
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: day } as never;
    if (path.endsWith('/insight')) return payload() as never;
    if (path.endsWith('/grade-history')) return { student_id: 'ada', active_section_id: 'class', sections: [] } as never;
    if (path === '/students/ada') return detail() as never;
    throw new Error(`Unexpected request ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}><Routes><Route path="/students/:id" element={<Student />} /></Routes></MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  await screen.findByText('Insight calculations through 2026-10-01');
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/calendar')).toHaveLength(1);
  day = '2026-10-02';
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: day }); });
  expect(await screen.findByText('Recorded metrics calculated through 2026-10-02')).toBeInTheDocument();
  expect(screen.getByText('Insight calculations through 2026-10-01')).toBeInTheDocument();
  expect(reads()).toHaveLength(1);
});


it('actual Root logout and same-ID relogin isolate old pending completion from a new refresh', async () => {
  const element = document.createElement('div'); element.id = 'root'; document.body.append(element);
  let Root: typeof import('../main')['Root'];
  try { ({ Root } = await import('../main')); } finally { element.remove(); }
  const oldRead = deferred<InsightData>(); const newRead = deferred<InsightData>();
  let oldSignal: AbortSignal | undefined; let requests = 0;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/auth/login' || path === '/auth/logout') return {} as never;
    if (path === '/calendar') return { timezone: 'UTC', today: '2026-10-02' } as never;
    if (path.endsWith('/insight')) {
      requests += 1;
      if (requests === 2) { oldSignal = options?.signal; return oldRead.promise as never; }
      if (requests === 4) return newRead.promise as never;
      return { ...payload(), headline: requests === 1 ? 'Old session advice' : 'New session advice' } as never;
    }
    throw new Error(`Unexpected request ${path}`);
  });
  const clients: QueryClient[] = []; let logout!: () => void;
  function Probe() {
    const client = useQueryClient(); if (!clients.includes(client)) clients.push(client);
    logout = useAuth().logout;
    return <Insight id="ada" />;
  }
  render(<Root><Probe /></Root>);
  await screen.findByText('Old session advice');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh insight' }));
  await waitFor(() => expect(requests).toBe(2)); const old = clients.at(-1)!;
  await act(async () => logout()); await screen.findByRole('heading', { name: 'Sign in' });
  expect(oldSignal?.aborted).toBe(true); expect(old.getQueryCache().getAll()).toHaveLength(0);
  const user = userEvent.setup(); await user.type(screen.getByLabelText('Passcode'), 'new-passcode');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByText('New session advice'); const current = clients.at(-1)!; expect(current).not.toBe(old);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh insight' })); await waitFor(() => expect(requests).toBe(4));
  await act(async () => oldRead.resolve({ ...payload(), headline: 'Obsolete session completion' }));
  expect(screen.queryByText('Obsolete session completion')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Refresh insight' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh insight' })); expect(requests).toBe(4);
  await act(async () => newRead.resolve({ ...payload('2026-10-02'), headline: 'Fresh session advice' }));
  await screen.findByText('Fresh session advice');
  expect(current.getQueryData(['insight', 'ada'])).toEqual({ ...payload('2026-10-02'), headline: 'Fresh session advice' });
  expect(old.getQueryCache().getAll()).toHaveLength(0);
});
