import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { EditAssessment } from '../pages/Gradebook';
import type { AssessmentOut, Gradebook } from '../types';
import { api } from '../api';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const assessment: AssessmentOut = { id: 'quiz-1', section_id: 'section-1', title: 'Quiz', kind: 'quiz', max_points: 10, due_date: '2026-10-01' };
const gradebook: Gradebook = { as_of: '2026-10-01', section: { id: 'section-1', course_id: 'course-1', name: 'Period 1' }, assessments: [assessment], rows: [] };
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onClose = vi.fn();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}><ToastProvider><EditAssessment assessment={assessment} onClose={onClose} /></ToastProvider></QueryClientProvider>);
  return { user: userEvent.setup(), onClose, invalidate, client };
}
beforeEach(() => { vi.mocked(api).mockReset(); vi.mocked(api).mockResolvedValue(gradebook); });
describe('Assessment editing', () => {
  it('sends edited fields to the exact assessment, warns about recalculation, and refreshes affected caches', async () => {
    const { user, onClose, invalidate, client } = setup();
    await user.clear(screen.getByLabelText('Title')); await user.type(screen.getByLabelText('Title'), 'Final quiz');
    await user.selectOptions(screen.getByLabelText('Type'), 'test');
    await user.clear(screen.getByLabelText('Max points')); await user.type(screen.getByLabelText('Max points'), '20');
    expect(within(screen.getByRole('dialog')).getByRole('status')).toHaveTextContent("keeps every student's raw score unchanged");
    await user.click(screen.getByRole('button', { name: 'Save assignment' }));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledWith('/assessments/quiz-1', { method: 'PATCH', body: { title: 'Final quiz', kind: 'test', max_points: 20, due_date: '2026-10-01' } });
    expect(client.getQueryData(['gradebook', 'section-1'])).toEqual(gradebook);
    for (const key of ['overview', 'student', 'insight', 'report-summary']) expect(invalidate).toHaveBeenCalledWith({ queryKey: [key] });
  });
  it('blocks blank titles and nonpositive maximums', async () => {
    const { user } = setup();
    await user.clear(screen.getByLabelText('Title')); await user.type(screen.getByLabelText('Title'), '   ');
    expect(screen.getByRole('button', { name: 'Save assignment' })).toBeDisabled();
    await user.type(screen.getByLabelText('Title'), 'Quiz');
    await user.clear(screen.getByLabelText('Max points')); await user.type(screen.getByLabelText('Max points'), '0');
    expect(screen.getByRole('button', { name: 'Save assignment' })).toBeDisabled();
    expect(api).not.toHaveBeenCalled();
  });
  it('keeps the draft and dialog open when saving fails', async () => {
    vi.mocked(api).mockRejectedValue(new Error('Save failed'));
    const { user, onClose, client } = setup();
    await user.clear(screen.getByLabelText('Title')); await user.type(screen.getByLabelText('Title'), 'Retry quiz');
    await user.click(screen.getByRole('button', { name: 'Save assignment' }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Save failed');
    expect(screen.getByLabelText('Title')).toHaveValue('Retry quiz');
    expect(onClose).not.toHaveBeenCalled();
    expect(client.getQueryData(['gradebook', 'section-1'])).toBeUndefined();
  });
});
