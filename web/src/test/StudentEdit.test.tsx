import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { EditStudent, StudentProfile } from '../pages/Student';
import type { CourseOut, StudentDetail } from '../types';
import { ApiError, api } from '../api';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
const student: StudentDetail = { as_of: '2026-10-01', id: 'student-1', name: 'Ada', grade_level: 9, section_id: 'section-1', section: 'Period 1', course_id: 'course-1', course: 'Math', average: 80, letter: 'B', gpa: 3, trend: 0, attendance_rate: 100, homework_rate: 100, missing: 0, risk: 'on_track', risk_reasons: [], scores: [], attendance: [], absences: 0, tardies: 0, notes: [] };
const courses: CourseOut[] = [{ id: 'course-1', name: 'Math', sections: [{ id: 'section-1', name: 'Period 1', course_id: 'course-1' }, { id: 'section-2', name: 'Period 2', course_id: 'course-1' }] }];
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  client.setQueryData(['courses'], courses);
  const onClose = vi.fn();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  render(<QueryClientProvider client={client}><ToastProvider><EditStudent student={student} onClose={onClose} /></ToastProvider></QueryClientProvider>);
  return { user: userEvent.setup(), client, onClose, invalidate };
}
beforeEach(() => { vi.mocked(api).mockReset(); vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? courses : { ...student, name: 'Ada Lovelace', grade_level: 10 }); });
describe('Student profile editing', () => {
  it('updates the exact student and refreshes profile, roster and reporting caches', async () => {
    const { user, onClose, invalidate, client } = setup();
    await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), '  Ada Lovelace  ');
    await user.clear(screen.getByLabelText('Grade level')); await user.type(screen.getByLabelText('Grade level'), '10');
    await user.click(screen.getByRole('button', { name: 'Save student' }));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledWith('/students/student-1', { method: 'PATCH', body: { name: 'Ada Lovelace', grade_level: 10, section_id: 'section-1' } });
    expect(client.getQueryData<StudentDetail>(['student', 'student-1'])?.name).toBe('Ada Lovelace');
    for (const key of ['student', 'students', 'overview', 'gradebook', 'report-summary', 'insight', 'grade-history']) expect(invalidate).toHaveBeenCalledWith({ queryKey: [key] });
  });
  it('blocks blank names and grades outside 1 through 12, including fractions', async () => {
    const { user } = setup();
    await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), '  ');
    expect(screen.getByRole('button', { name: 'Save student' })).toBeDisabled();
    await user.type(screen.getByLabelText('Name'), 'Ada');
    for (const grade of ['0', '13', '9.5']) {
      await user.clear(screen.getByLabelText('Grade level')); await user.type(screen.getByLabelText('Grade level'), grade);
      expect(screen.getByRole('button', { name: 'Save student' })).toBeDisabled();
    }
    expect(vi.mocked(api).mock.calls.some(([path]) => path.startsWith('/students/'))).toBe(false);
  });
  it('explains history preservation and keeps draft fields after a failed move', async () => {
    vi.mocked(api).mockImplementation(async (path) => { if (path === '/courses') return courses; throw new ApiError(503, 'Save failed'); });
    const { user, onClose, invalidate, client } = setup();
    client.setQueryData(['student', student.id], student);
    await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'Ada Revised');
    await user.selectOptions(screen.getByLabelText('Section'), 'section-2');
    expect(within(screen.getByRole('dialog')).getByRole('status')).toHaveTextContent('preserves grade history');
    await user.click(screen.getByRole('button', { name: 'Save student' }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Save failed');
    expect(screen.getByLabelText('Name')).toHaveValue('Ada Revised');
    expect(screen.getByLabelText('Section')).toHaveValue('section-2');
    expect(client.getQueryData(['student', student.id])).toEqual(student);
    expect(invalidate).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
  it('isolates an in-flight save when navigating to another student', async () => {
    let finishSave: ((value: StudentDetail) => void) | undefined;
    vi.mocked(api).mockImplementation((path) => path === '/courses' ? Promise.resolve(courses) : new Promise<StudentDetail>((resolve) => { finishSave = resolve; }));
    const client = new QueryClient();
    client.setQueryData(['courses'], courses);
    const show = (detail: StudentDetail) => <QueryClientProvider client={client}><ToastProvider><StudentProfile key={detail.id} student={detail} /></ToastProvider></QueryClientProvider>;
    const view = render(show(student));
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Edit student' }));
    await user.clear(screen.getByLabelText('Name')); await user.type(screen.getByLabelText('Name'), 'First draft');
    await user.click(screen.getByRole('button', { name: 'Save student' }));
    await vi.waitFor(() => expect(finishSave).toBeDefined());
    const second = { ...student, id: 'student-2', name: 'Ben' };
    view.rerender(show(second));
    await user.click(screen.getByRole('button', { name: 'Edit student' }));
    expect(screen.getByLabelText('Name')).toHaveValue('Ben');
    await act(async () => { finishSave?.({ ...student, name: 'First draft' }); });
    await vi.waitFor(() => expect(client.getQueryData<StudentDetail>(['student', 'student-1'])?.name).toBe('First draft'));
    expect(screen.getByLabelText('Name')).toHaveValue('Ben');
    expect(client.getQueryData(['student', 'student-2'])).toBeUndefined();
  });
});
