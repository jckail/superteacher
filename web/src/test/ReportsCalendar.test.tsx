import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, UNAUTHORIZED_EVENT } from '../api';
import { AuthGate, clearPrivateSession } from '../auth';
import Reports from '../pages/Reports';
import type { ClassSummary, ParentUpdateOut, Section, StudentPage } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
const { scope } = vi.hoisted(() => ({ scope: { ready: true, section: { id: 'p1', course_id: 'math', name: 'P1' } } }));
vi.mock('../scope', () => ({ useActiveSection: () => scope.ready ? scope.section : undefined, useScope: () => ({ ready: scope.ready, isLoading: false, setSection: vi.fn() }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => <span>Scope picker</span> }));
vi.mock('../components/ScopeStatus', () => ({ default: () => scope.ready ? null : <p>Resolve saved scope</p> }));

function summary(as_of = '2026-09-30', sectionId = 'p1'): ClassSummary {
  const due = as_of >= '2026-10-01';
  return { as_of, section_id: sectionId, section: sectionId, course: 'Math', students: 1, unknown: due ? 0 : 1, on_track: due ? 1 : 0, watch: 0, at_risk: 0, average: due ? 90 : null, distribution: { A: due ? 1 : 0, B: 0, C: 0, D: 0, F: 0 }, assessments: [{ id: 'quiz', title: 'Tomorrow quiz', kind: 'quiz', due_date: '2026-10-01', max_points: 10, graded: due ? 1 : 0, average: due ? 90 : null, median: due ? 90 : null, min: due ? 90 : null, max: due ? 90 : null, missing_pct: due ? 0 : null }], attention: [], attendance: due ? [{ day: '2026-10-01', rate: 100, marked: 1, absent: 0 }] : [], attendance_rate: due ? 100 : null };
}
function students(sectionId = 'p1'): StudentPage {
  return { items: [{ id: 'ada', name: 'Ada', grade_level: 4, section_id: sectionId, section: sectionId, course_id: 'math', course: 'Math', average: null, letter: null, gpa: null, trend: null, attendance_rate: null, homework_rate: null, missing: 0, risk: 'unknown', risk_reasons: [] }], next_cursor: null, as_of: '2026-09-30', total_scoped: 1, total_matches: 1 };
}
const draft: ParentUpdateOut = { subject: 'Ada update', body: 'Original draft', source: 'template' };
function client() { return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } }); }
function frame(qc: QueryClient, children: ReactNode = <Reports />) { return <QueryClientProvider client={qc}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>; }
function setup(qc = client()) { return { ...render(frame(qc)), client: qc, user: userEvent.setup() }; }
function calls(kind: 'summary' | 'generation' | 'students') { return vi.mocked(api).mock.calls.filter(([path]) => kind === 'summary' ? path.endsWith('/summary') : kind === 'generation' ? path.endsWith('/parent-update') : path.startsWith('/students/page')); }
function mockReads(read: (section: Section) => ClassSummary | Promise<ClassSummary>, generate: () => ParentUpdateOut | Promise<ParentUpdateOut> = () => draft) {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (path.endsWith('/summary')) return read(scope.section) as never;
    if (path.endsWith('/parent-update')) return generate() as never;
    if (path.startsWith('/students/page')) return students(scope.section.id) as never;
    throw new Error('Unexpected synthetic request');
  });
}
async function day(qc: QueryClient, today = '2026-10-01') { await act(async () => { qc.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today }); }); }
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function stat(label: string) { return screen.getByText(label).closest('.stat')!; }
beforeEach(() => { vi.mocked(api).mockReset(); scope.ready = true; scope.section = { id: 'p1', course_id: 'math', name: 'P1' }; });

it('refreshes actual summary values after a validated school day advances without refetching the composer', async () => {
  let cutoff = '2026-09-30'; mockReads(() => summary(cutoff));
  const { client: qc } = setup();
  await screen.findByText('No graded work yet.');
  await screen.findByRole('option', { name: 'Ada' });
  expect(stat('Class average')).toHaveTextContent('—');
  cutoff = '2026-10-01'; await day(qc);
  await waitFor(() => expect(calls('summary')).toHaveLength(2));
  await waitFor(() => expect(stat('Class average')).toHaveTextContent('90%'));
  expect(screen.getByText('A: 1')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'Class average by assessment: Tomorrow quiz 90 percent' })).toBeInTheDocument();
  expect(screen.getByText('Summary calculated through 2026-10-01')).toBeInTheDocument();
  expect(qc.getQueryData<ClassSummary>(['report-summary', 'p1'])?.assessments[0].graded).toBe(1);
  expect(calls('students')).toHaveLength(1); expect(calls('generation')).toHaveLength(0);
  await day(qc); expect(calls('summary')).toHaveLength(2);
});

it.each(['success', 'failure'] as const)('preserves actual edited parent subject/body/selection through a summary refresh %s', async (outcome) => {
  let cutoff = '2026-09-30';
  mockReads(() => { if (calls('summary').length > 1 && outcome === 'failure') throw new Error('Summary refresh failed'); return summary(cutoff); });
  const { client: qc, user } = setup();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByRole('combobox', { name: /^Student/ }), 'ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  await screen.findByLabelText('Subject');
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Edited subject' } });
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Keep my private edit' } });
  cutoff = '2026-10-01'; await day(qc);
  if (outcome === 'success') await screen.findByText('Summary calculated through 2026-10-01');
  else {
    await screen.findByText('Summary refresh failed');
    expect(screen.getByText('Summary calculated through 2026-09-30')).toBeInTheDocument();
    expect(screen.getByText('No graded work yet.')).toBeInTheDocument();
    expect(screen.getByText(/Refresh failed. Use Retry to update the summary/)).toHaveAttribute('role', 'status');
    expect(screen.queryByText('No students in this section yet. Add some on the roster.')).not.toBeInTheDocument();
  }
  expect(screen.getByLabelText('Subject')).toHaveValue('Edited subject');
  expect(screen.getByLabelText('Message')).toHaveValue('Keep my private edit');
  expect(screen.getByRole('combobox', { name: /^Student/ })).toHaveValue('ada');
  expect(calls('generation')).toHaveLength(1); expect(calls('students')).toHaveLength(1);
  await day(qc); expect(calls('summary')).toHaveLength(2);
});

it('keeps a genuine pending parent generation captured across a completed summary rollover without duplicate requests', async () => {
  const pending = deferred<ParentUpdateOut>();
  let cutoff = '2026-09-30'; mockReads(() => summary(cutoff), () => pending.promise);
  const { client: qc, user } = setup();
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByRole('combobox', { name: /^Student/ }), 'ada');
  const generate = screen.getByRole('button', { name: 'Generate draft' });
  act(() => { fireEvent.click(generate); fireEvent.click(generate); });
  expect(calls('generation')).toHaveLength(1);
  cutoff = '2026-10-01'; await day(qc);
  await screen.findByText('Summary calculated through 2026-10-01');
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: /^Student/ })).toHaveValue('ada');
  expect(calls('generation')[0][1]?.body).toEqual({ tone: 'warm', expected_section_id: 'p1' });
  await act(async () => pending.resolve(draft));
  expect(await screen.findByLabelText('Subject')).toHaveValue('Ada update');
  expect(screen.getByLabelText('Message')).toHaveValue('Original draft');
  expect(screen.getByRole('button', { name: 'Regenerate' })).toBeEnabled();
  expect(calls('generation')).toHaveLength(1); expect(calls('students')).toHaveLength(1);
});

it('retains old rows after a failed read and succeeds only after explicit retry', async () => {
  let fail = true;
  mockReads(() => { if (calls('summary').length > 1 && fail) throw new Error('Read unavailable'); return summary(calls('summary').length > 1 ? '2026-10-01' : '2026-09-30'); });
  const { client: qc, user } = setup();
  await screen.findByText('Summary calculated through 2026-09-30');
  await day(qc); await screen.findByText('Read unavailable');
  expect(stat('Class average')).toHaveTextContent('—');
  expect(qc.getQueryData<ClassSummary>(['report-summary', 'p1'])?.students).toBe(1);
  await day(qc); expect(calls('summary')).toHaveLength(2);
  fail = false; await user.click(screen.getByRole('button', { name: /^Retry$/ }));
  await screen.findByText('Summary calculated through 2026-10-01');
  expect(stat('Class average')).toHaveTextContent('90%');
  expect(calls('summary')).toHaveLength(3);
});

it.each(['fresh', 'older'] as const)('coalesces calendar advancement during an invalidated summary read returning a %s cutoff', async (outcome) => {
  const pending = deferred<ClassSummary>();
  let manual = false;
  mockReads(() => calls('summary').length === 2 ? pending.promise : summary(manual ? '2026-10-01' : '2026-09-30'));
  const { client: qc, user } = setup();
  await screen.findByText('Summary calculated through 2026-09-30');
  await act(async () => { void qc.invalidateQueries({ queryKey: ['report-summary'] }); });
  await waitFor(() => expect(calls('summary')).toHaveLength(2));
  await day(qc);
  await screen.findByText(/Updating school-day calculations/);
  expect(calls('summary')).toHaveLength(2);
  await act(async () => pending.resolve(summary(outcome === 'fresh' ? '2026-10-01' : '2026-09-30')));
  if (outcome === 'fresh') {
    await screen.findByText('Summary calculated through 2026-10-01');
    expect(stat('Class average')).toHaveTextContent('90%');
    expect(calls('summary')).toHaveLength(2);
  } else {
    await screen.findByRole('button', { name: 'Refresh summary' });
    expect(calls('summary')).toHaveLength(3);
    await day(qc); expect(calls('summary')).toHaveLength(3);
    manual = true; await user.click(screen.getByRole('button', { name: 'Refresh summary' }));
    await screen.findByText('Summary calculated through 2026-10-01');
    expect(calls('summary')).toHaveLength(4);
  }
  expect(calls('generation')).toHaveLength(0); expect(calls('students')).toHaveLength(1);
});

it.each(['section', 'readiness'] as const)('restarts a bounded attempt after %s ABA returns to the same stale section', async (transition) => {
  let p1Reads = 0;
  mockReads((section) => summary(section.id === 'p1' && ++p1Reads < 3 ? '2026-09-30' : '2026-10-01', section.id));
  const { client: qc, rerender } = setup();
  await screen.findByText('Summary calculated through 2026-09-30');
  await day(qc); await screen.findByRole('button', { name: 'Refresh summary' });
  expect(p1Reads).toBe(2);
  if (transition === 'section') scope.section = { id: 'p2', course_id: 'math', name: 'P2' };
  else scope.ready = false;
  rerender(frame(qc));
  if (transition === 'section') await screen.findByText('Summary calculated through 2026-10-01');
  else {
    await screen.findByText('Resolve saved scope');
    expect(screen.queryByText(/Summary calculated through/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Refresh summary' })).not.toBeInTheDocument();
  }
  scope.ready = true; scope.section = { id: 'p1', course_id: 'math', name: 'P1' };
  rerender(frame(qc));
  await waitFor(() => expect(p1Reads).toBe(3));
  await screen.findByText('Summary calculated through 2026-10-01');
  expect(qc.getQueryData<ClassSummary>(['report-summary', 'p1'])?.average).toBe(90);
  await day(qc); expect(p1Reads).toBe(3);
});

it('aborts a superseded section read and ignores its late result even after returning to the original section', async () => {
  const pending = deferred<ClassSummary>(); let p1Reads = 0, signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (path.endsWith('/summary')) {
      if (path.includes('/p1/')) {
        if (++p1Reads === 1) return summary() as never;
        if (p1Reads === 2) { signal = options?.signal; return pending.promise as never; }
      }
      return summary('2026-10-01', scope.section.id) as never;
    }
    return students(scope.section.id) as never;
  });
  const { client: qc, rerender } = setup();
  await screen.findByText('Summary calculated through 2026-09-30'); await day(qc);
  await waitFor(() => expect(p1Reads).toBe(2));
  scope.section = { id: 'p2', course_id: 'math', name: 'P2' }; rerender(frame(qc));
  await screen.findByText('Summary calculated through 2026-10-01');
  expect(signal?.aborted).toBe(true);
  scope.section = { id: 'p1', course_id: 'math', name: 'P1' }; rerender(frame(qc));
  await waitFor(() => expect(p1Reads).toBe(3));
  await screen.findByText('Summary calculated through 2026-10-01');
  await act(async () => pending.resolve(summary()));
  expect(stat('Class average')).toHaveTextContent('90%');
  expect(qc.getQueryData<ClassSummary>(['report-summary', 'p1'])?.as_of).toBe('2026-10-01');
});

it('labels a genuinely empty old cache and refreshes it when reopened', async () => {
  const qc = client(); const empty = { ...summary(), students: 0, unknown: 0, assessments: [] };
  qc.setQueryData(['report-summary', 'p1'], empty);
  mockReads(() => ({ ...empty, as_of: '2026-10-01' }));
  qc.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-01' });
  setup(qc);
  await screen.findByText('No students in this section yet. Add some on the roster.');
  await screen.findByText('Summary calculated through 2026-10-01');
  expect(calls('summary')).toHaveLength(1);
  expect(screen.queryByText('Class average')).not.toBeInTheDocument();
});

it('makes a cold initial summary error retryable without inventing a cutoff or empty rows', async () => {
  let fail = true; mockReads(() => { if (fail) throw new Error('Initial summary failed'); return summary(); });
  const { user } = setup();
  await screen.findByText('Initial summary failed');
  expect(screen.queryByText(/Summary calculated through/)).not.toBeInTheDocument();
  expect(screen.queryByText('No students in this section yet. Add some on the roster.')).not.toBeInTheDocument();
  fail = false; await user.click(screen.getByRole('button', { name: /^Retry$/ }));
  await screen.findByText('Summary calculated through 2026-09-30');
  expect(calls('summary')).toHaveLength(2);
});

it('retains its real server cutoff through calendar failure and hides recovery controls when scope is unready', async () => {
  let fail = true;
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') { if (fail) throw new Error('Calendar unavailable'); return { timezone: 'America/Los_Angeles', today: '2000-01-01' } as never; }
    return (path.endsWith('/summary') ? summary('2000-01-01') : students()) as never;
  });
  const { client: qc, user, rerender } = setup();
  await screen.findByText('Summary calculated through 2000-01-01'); await screen.findByText('Calendar unavailable');
  expect(stat('Class average')).toHaveTextContent('—');
  scope.ready = false; rerender(frame(qc));
  expect(screen.queryByText('Calendar unavailable')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Retry school calendar' })).not.toBeInTheDocument();
  scope.ready = true; rerender(frame(qc));
  await screen.findByRole('button', { name: 'Retry school calendar' });
  fail = false; await user.click(screen.getByRole('button', { name: 'Retry school calendar' }));
  await waitFor(() => expect(screen.queryByText('Calendar unavailable')).not.toBeInTheDocument());
  expect(screen.getByText('Summary calculated through 2000-01-01')).toBeInTheDocument();
  expect(calls('summary')).toHaveLength(1);
});

it('does not move a newer response cutoff backwards to match an older calendar', async () => {
  mockReads(() => summary('2026-10-01'));
  const { client: qc } = setup(); await screen.findByText('Summary calculated through 2026-10-01');
  expect(screen.queryByRole('button', { name: 'Refresh summary' })).not.toBeInTheDocument();
  await day(qc, '2026-09-30'); expect(calls('summary')).toHaveLength(1);
});

it('clears pending private summary work at the actual auth boundary and rejects late completion', async () => {
  const pending = deferred<ClassSummary>(); let reads = 0, signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { auth_required: true } as never;
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-09-30' } as never;
    if (path.endsWith('/summary')) { if (++reads === 1) return summary() as never; signal = options?.signal; return pending.promise as never; }
    return students() as never;
  });
  const qc = client(); render(frame(qc, <AuthGate onLogout={() => clearPrivateSession(qc)}><Reports /></AuthGate>));
  await screen.findByText('Summary calculated through 2026-09-30'); await day(qc);
  await waitFor(() => expect(reads).toBe(2));
  await act(async () => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
  expect(signal?.aborted).toBe(true);
  expect(screen.queryByText(/Summary calculated through/)).not.toBeInTheDocument();
  await act(async () => pending.resolve(summary('2026-10-01')));
  expect(qc.getQueryData(['report-summary', 'p1'])).toBeUndefined();
});
