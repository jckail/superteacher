import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { ToastProvider } from '../components/Toast';
import { ConfirmProvider } from '../components/Confirm';
import Attendance from '../pages/Attendance';
import { NewAssessment } from '../pages/Gradebook';
import Student from '../pages/Student';
import type { StudentDetail } from '../types';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
vi.mock('../scope', () => ({ useActiveSection: () => ({ id: 'class', course_id: 'math', name: 'Math' }), useScope: () => ({ isLoading: false }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
function setup(page: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><MemoryRouter initialEntries={['/students/ada']}>{page}</MemoryRouter></ConfirmProvider></ToastProvider></QueryClientProvider>);
  return { client, user: userEvent.setup() };
}
beforeEach(() => { vi.mocked(api).mockReset(); });

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
  expect(date).toHaveValue('2026-09-29');
  expect(date).toHaveAttribute('max', '2026-10-01');
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
  await act(async () => { finish({ section: { id: 'class', course_id: 'math', name: 'Math' }, assessments: [], rows: [] }); });
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
