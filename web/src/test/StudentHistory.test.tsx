import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { GradeHistory } from '../pages/Student';
import type { GradeHistoryOut } from '../types';
import { api } from '../api';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const history: GradeHistoryOut = {
  student_id: 'ada', active_section_id: 'new-section', sections: [{
    section_id: 'old-section', section: 'Period 1', course_id: 'math', course: 'Math', scores: [
      { assessment_id: 'quiz', title: 'Prior quiz', kind: 'quiz', due_date: '2026-09-01', points: 0, max_points: 20, pct: 0 },
      { assessment_id: 'homework', title: 'Prior homework', kind: 'homework', due_date: '2026-09-02', points: null, max_points: 10, pct: null },
    ],
  }],
};
function setup(studentId = 'ada', sectionId = 'new-section') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const show = (id: string, sid: string) => <QueryClientProvider client={client}><GradeHistory studentId={id} activeSectionId={sid} /></QueryClientProvider>;
  return { ...render(show(studentId, sectionId)), show, client, user: userEvent.setup() };
}
beforeEach(() => { vi.mocked(api).mockReset(); vi.mocked(api).mockResolvedValue(history); });

it('shows scoped previous-section zero and unrecorded scores without current missing claims', async () => {
  setup();
  const table = await screen.findByRole('table', { name: 'Grades from Math · Period 1' });
  expect(within(table).getByText('0/20 (0%)')).toBeInTheDocument();
  expect(within(table).getByText('Not recorded')).toBeInTheDocument();
  expect(within(table).queryByText('missing')).not.toBeInTheDocument();
  expect(screen.getByText(/do not affect the current-section average/)).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith('/students/ada/grade-history', { signal: expect.any(AbortSignal) });
});

it('shows an empty history clearly', async () => {
  vi.mocked(api).mockResolvedValue({ ...history, sections: [] });
  setup();
  expect(await screen.findByText('No grades from previous sections.')).toBeInTheDocument();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('offers retry after a history request fails', async () => {
  vi.mocked(api).mockRejectedValueOnce(new Error('History unavailable')).mockResolvedValue(history);
  const { user } = setup();
  expect(await screen.findByRole('alert')).toHaveTextContent('History unavailable');
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByText('Prior quiz')).toBeInTheDocument();
});

it('does not show a late previous-student response on the next profile', async () => {
  let finish: ((value: GradeHistoryOut) => void) | undefined;
  vi.mocked(api).mockImplementation((path) => path.includes('/ada/') ? new Promise<GradeHistoryOut>((resolve) => { finish = resolve; }) : Promise.resolve({ student_id: 'ben', active_section_id: 'new-section', sections: [] }));
  const view = setup();
  await vi.waitFor(() => expect(finish).toBeDefined());
  view.rerender(view.show('ben', 'new-section'));
  await screen.findByText('No grades from previous sections.');
  await act(async () => { finish?.(history); });
  expect(screen.queryByText('Prior quiz')).not.toBeInTheDocument();
});

it('requires refresh when response describes the previous active section', async () => {
  vi.mocked(api).mockResolvedValue({ ...history, active_section_id: 'old-section' });
  setup();
  expect(await screen.findByText(/section changed/)).toBeInTheDocument();
  expect(screen.queryByText('Prior quiz')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Refresh grade history' })).toBeInTheDocument();
});
