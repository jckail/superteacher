import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Attendance from '../pages/Attendance';
import Reports from '../pages/Reports';
import { ScoreCell } from '../pages/Gradebook';
import type { AttendanceSheet, ClassSummary, ParentUpdateOut, Section, StudentSummary } from '../types';
const { request } = vi.hoisted(() => ({ request: vi.fn() }));
const section: Section = { id: 'section-1', course_id: 'course-1', name: 'Class A' };
const emptySummary: ClassSummary = { as_of: '2026-10-01', section_id: section.id, section: section.name, course: 'Math', students: 0, unknown: 0, on_track: 0, watch: 0, at_risk: 0, average: null, distribution: { A: 0, B: 0, C: 0, D: 0, F: 0 }, assessments: [], attention: [], attendance: [], attendance_rate: null };
vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: request }));
vi.mock('../scope', () => ({ useActiveSection: () => section, useScope: () => ({ isLoading: false, ready: true }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((success, failure) => { resolve = success; reject = failure; });
  return { promise, resolve, reject };
}
function mount(page: 'attendance' | 'reports') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  client.setQueryData(['school-calendar'], { timezone: 'UTC', today: '2026-10-01' });
  render(<QueryClientProvider client={client}><MemoryRouter>{page === 'attendance' ? <Attendance /> : <Reports />}</MemoryRouter></QueryClientProvider>);
  return { client, user: userEvent.setup() };
}
function student(id: string, name: string): StudentSummary {
  return { id, name, grade_level: 4, section_id: section.id, section: section.name, course_id: section.course_id, course: 'Math', average: null, letter: null, gpa: null, trend: null, attendance_rate: null, homework_rate: null, missing: 0, risk: 'unknown', risk_reasons: [] };
}
beforeEach(() => { request.mockReset(); });
describe('operations request races', () => {
  it('keeps a newer score draft when an earlier save fails', async () => {
    const pending = deferred<void>();
    const save = vi.fn(() => pending.promise);
    render(<ScoreCell value={7} max={10} label="Score" onSave={save} />);
    const user = userEvent.setup();
    const input = screen.getByRole('textbox', { name: 'Score' });
    await user.clear(input);
    await user.type(input, '3');
    await user.tab();
    await user.clear(input);
    await user.type(input, '9');
    await act(async () => { pending.reject(new Error('failed')); });
    expect(input).toHaveValue('9');
  });
  it('rejects nonfinite scores without saving', async () => {
    const save = vi.fn();
    render(<ScoreCell value={7} max={10} label="Score" onSave={save} />);
    const user = userEvent.setup();
    const input = screen.getByRole('textbox', { name: 'Score' });
    await user.clear(input);
    await user.type(input, 'Infinity');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    await user.tab();
    expect(save).not.toHaveBeenCalled();
    expect(input).toHaveValue('7');
  });
  it('preserves another student’s optimistic attendance when an overlapping save fails', async () => {
    const first = deferred<AttendanceSheet>();
    const second = deferred<AttendanceSheet>();
    const sheet: AttendanceSheet = { section, day: '2026-10-01', rows: [{ student_id: 'ada', name: 'Ada', status: null }, { student_id: 'bob', name: 'Bob', status: null }] };
    request.mockImplementation((_path: string, options?: { method?: string; body?: { marks: { student_id: string }[] } }) => options?.method === 'PUT' ? (options.body?.marks[0].student_id === 'ada' ? first.promise : second.promise) : Promise.resolve(sheet));
    const { user, client } = mount('attendance');
    const ada = await screen.findByRole('group', { name: 'Attendance for Ada' });
    const bob = screen.getByRole('group', { name: 'Attendance for Bob' });
    await user.click(within(ada).getByRole('button', { name: 'Present' }));
    await user.click(within(bob).getByRole('button', { name: 'Tardy' }));
    await waitFor(() => expect(within(bob).getByRole('button', { name: 'Tardy' })).toHaveAttribute('aria-pressed', 'true'));
    await act(async () => { first.reject(new Error('failed')); });
    await waitFor(() => expect(within(ada).getByRole('button', { name: 'Present' })).toHaveAttribute('aria-pressed', 'false'));
    expect(within(bob).getByRole('button', { name: 'Tardy' })).toHaveAttribute('aria-pressed', 'true');
    sheet.rows[1].status = 'tardy';
    await act(async () => { second.resolve(sheet); });
    client.clear();
  });
  it('discards a completed parent draft after the selected student changes', async () => {
    const pending = deferred<ParentUpdateOut>();
    request.mockImplementation((path: string) => {
      if (path.endsWith('/summary')) return Promise.resolve(emptySummary);
      if (path.startsWith('/students?')) return Promise.resolve([student('ada', 'Ada'), student('bob', 'Bob')]);
      if (path.endsWith('/parent-update')) return pending.promise;
      throw new Error(`Unexpected request: ${path}`);
    });
    const { user, client } = mount('reports');
    const select = await screen.findByRole('combobox', { name: 'Student' });
    await screen.findByRole('option', { name: 'Ada' });
    await user.selectOptions(select, 'ada');
    await user.click(screen.getByRole('button', { name: 'Generate draft' }));
    await user.selectOptions(select, 'bob');
    await act(async () => { pending.resolve({ subject: 'Ada update', body: 'Ada grades', source: 'template' }); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft' })).toBeEnabled());
    expect(screen.queryByRole('textbox', { name: 'Subject' })).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Student' })).toHaveValue('bob');
    client.clear();
  });
});
