import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { ConfirmProvider } from '../components/Confirm';
import { Notes } from '../pages/Student';
import type { StudentDetail } from '../types';
import { api } from '../api';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const student: StudentDetail = { as_of: '2026-10-01', id: 'student-1', name: 'Ada', grade_level: 9, section_id: 'section-1', section: 'Period 1', course_id: 'course-1', course: 'Math', average: 80, letter: 'B', gpa: 3, trend: 0, attendance_rate: 100, homework_rate: 100, missing: 0, risk: 'on_track', risk_reasons: [], scores: [], attendance: [], absences: 0, tardies: 0, notes: [{ id: 'note-1', body: 'Private observation', created_at: '2026-10-01T00:00:00Z' }] };
function setup() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}><ToastProvider><ConfirmProvider><Notes student={student} /></ConfirmProvider></ToastProvider></QueryClientProvider>);
  return { user: userEvent.setup(), invalidate };
}
beforeEach(() => { vi.mocked(api).mockReset(); vi.mocked(api).mockResolvedValue(student.notes[0]); });
describe('Private student notes', () => {
  it('edits within the student scope and invalidates student and insight data', async () => {
    const { user, invalidate } = setup();
    await user.click(screen.getByRole('button', { name: 'Edit note: Private observation' }));
    await user.clear(screen.getByLabelText('Note')); await user.type(screen.getByLabelText('Note'), '  Revised observation  ');
    await user.click(screen.getByRole('button', { name: 'Save note' }));
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api).toHaveBeenCalledWith('/students/student-1/notes/note-1', { method: 'PATCH', body: { body: 'Revised observation' } });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['student', 'student-1'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['insight', 'student-1'] });
  });
  it('requires confirmation and permits canceling deletion', async () => {
    const { user } = setup();
    await user.click(screen.getByRole('button', { name: 'Delete note: Private observation' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }));
    expect(api).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Delete note: Private observation' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete note' }));
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/students/student-1/notes/note-1', { method: 'DELETE' }));
  });
  it('blocks whitespace notes and preserves drafts after failed saves', async () => {
    vi.mocked(api).mockRejectedValue(new Error('Save failed'));
    const { user, invalidate } = setup();
    await user.click(screen.getByRole('button', { name: 'Edit note: Private observation' }));
    await user.clear(screen.getByLabelText('Note')); await user.type(screen.getByLabelText('Note'), '   ');
    expect(screen.getByRole('button', { name: 'Save note' })).toBeDisabled();
    await user.type(screen.getByLabelText('Note'), 'Keep this draft');
    await user.click(screen.getByRole('button', { name: 'Save note' }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Save failed');
    expect(screen.getByLabelText('Note')).toHaveValue('   Keep this draft');
    expect(invalidate).not.toHaveBeenCalled();
  });
  it('reports failed deletion and preserves the displayed note', async () => {
    vi.mocked(api).mockRejectedValue(new Error('Delete failed'));
    const { user, invalidate } = setup();
    await user.click(screen.getByRole('button', { name: 'Delete note: Private observation' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete note' }));
    expect(await screen.findByText(/Couldn’t delete note: Delete failed/)).toBeInTheDocument();
    expect(screen.getByText('Private observation')).toBeInTheDocument();
    expect(invalidate).not.toHaveBeenCalled();
  });
});
