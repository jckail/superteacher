import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComponentType } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { ToastProvider } from '../components/Toast';
import { ImportDialog, NewClassDialog, NewStudentDialog } from '../pages/Roster';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
vi.mock('../scope', () => ({ useScope: () => ({
  courses: [{ id: 'math', name: 'Math', sections: [{ id: 'one', name: 'Period 1' }, { id: 'two', name: 'Period 2' }] }],
  allSections: [{ id: 'one', name: 'Period 1', course: 'Math' }, { id: 'two', name: 'Period 2', course: 'Math' }],
}) }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function setup(Dialog: ComponentType<{ onClose: () => void }> = ImportDialog) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const onClose = vi.fn();
  const view = render(<QueryClientProvider client={client}><ToastProvider><Dialog onClose={onClose} /></ToastProvider></QueryClientProvider>);
  return { ...view, onClose, invalidate, user: userEvent.setup() };
}
const fileInput = () => screen.getByLabelText('CSV file (columns: name, grade_level)');
function selectFile(name: string, promise: Promise<string>) {
  const file = new File([''], name, { type: 'text/csv' });
  Object.defineProperty(file, 'text', { value: () => promise });
  fireEvent.change(fileInput(), { target: { files: [file] } });
}
const importButton = () => screen.getByRole('button', { name: 'Import' });
const csv = 'name,grade_level\nAda,9';
beforeEach(() => { vi.mocked(api).mockReset(); });

describe('roster creation', () => {
  it('freezes a student write, blocks duplicate submits and all modal close paths, and retries a failed draft', async () => {
    const request = deferred<unknown>();
    vi.mocked(api).mockReturnValueOnce(request.promise).mockResolvedValueOnce({});
    const { user, onClose, invalidate } = setup(NewStudentDialog);
    await user.type(screen.getByLabelText('Name'), '  Ada  ');
    await user.selectOptions(screen.getByLabelText('Section'), 'two');
    const form = screen.getByLabelText('Name').closest('form')!;
    act(() => { fireEvent.submit(form); fireEvent.submit(form); });
    await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledWith('/students', { method: 'POST', body: { name: 'Ada', grade_level: 9, section_id: 'two' } });
    for (const label of ['Name', 'Grade level', 'Section']) expect(screen.getByLabelText(label)).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    await user.keyboard('{Escape}');
    fireEvent.mouseDown(screen.getByRole('dialog').parentElement!);
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => request.reject(new Error('Student write failed')));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Student write failed');
    expect(screen.getByLabelText('Name')).toHaveValue('  Ada  ');
    expect(invalidate).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Add student' }));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledTimes(2);
    expect(invalidate).toHaveBeenCalledOnce();
  });

  it('creates a new course and its initial section in one request and clears a failed result on edit', async () => {
    vi.mocked(api).mockRejectedValueOnce(new Error('Course write failed')).mockResolvedValueOnce({ id: 'science', name: 'Science', sections: [] });
    const { user, onClose } = setup(NewClassDialog);
    await user.type(screen.getByLabelText('Course name'), 'Biology');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Course write failed');
    expect(api).toHaveBeenCalledWith('/courses', { method: 'POST', body: { name: 'Biology', initial_section_name: 'Period 1' } });
    expect(api).toHaveBeenCalledOnce();
    await user.clear(screen.getByLabelText('Course name'));
    expect(within(screen.getByRole('dialog')).queryByRole('alert')).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Course name'), 'Science');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledTimes(2);
  });

  it('freezes section creation and prevents duplicate submits and dismissal until it settles', async () => {
    const request = deferred<unknown>();
    vi.mocked(api).mockReturnValueOnce(request.promise);
    const { user, onClose } = setup(NewClassDialog);
    await user.selectOptions(screen.getByLabelText('Add to'), 'math');
    await user.type(screen.getByLabelText('Section name'), 'Period 3');
    const form = screen.getByLabelText('Section name').closest('form')!;
    act(() => { fireEvent.submit(form); fireEvent.submit(form); });
    await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledWith('/sections', { method: 'POST', body: { course_id: 'math', name: 'Period 3' } });
    expect(screen.getByLabelText('Add to')).toBeDisabled();
    expect(screen.getByLabelText('Section name')).toBeDisabled();
    await user.keyboard('{Escape}');
    fireEvent.mouseDown(screen.getByRole('dialog').parentElement!);
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => request.resolve({}));
    await vi.waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });
});

describe('CSV import writes and file reads', () => {
  it('captures the draft once, blocks pending edits and dismissal, and preserves a failed import for retry', async () => {
    const request = deferred<unknown>();
    vi.mocked(api).mockReturnValueOnce(request.promise).mockResolvedValueOnce({ created: 1, skipped: [] });
    const { user, onClose, invalidate } = setup();
    fireEvent.change(screen.getByLabelText('CSV text'), { target: { value: csv } });
    await user.selectOptions(screen.getByLabelText('Section'), 'two');
    act(() => { fireEvent.click(importButton()); fireEvent.click(importButton()); });
    await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    expect(api).toHaveBeenCalledWith('/sections/two/import', { method: 'POST', body: { csv } });
    expect(screen.getByLabelText('CSV text')).toBeDisabled();
    expect(screen.getByLabelText('Section')).toBeDisabled();
    expect(fileInput()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    await user.keyboard('{Escape}');
    fireEvent.mouseDown(screen.getByRole('dialog').parentElement!);
    expect(onClose).not.toHaveBeenCalled();
    await act(async () => request.reject(new Error('Import failed')));
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Import failed');
    expect(screen.getByLabelText('CSV text')).toHaveValue(csv);
    expect(invalidate).not.toHaveBeenCalled();
    await user.click(importButton());
    expect(await within(screen.getByRole('dialog')).findByRole('status')).toHaveTextContent('1 added.');
    expect(api).toHaveBeenCalledTimes(2);
    expect(invalidate).toHaveBeenCalledOnce();
  });

  it('uses the latest file even when an older read resolves later, and blocks import during reading', async () => {
    setup();
    const old = deferred<string>(), latest = deferred<string>();
    selectFile('old.csv', old.promise);
    selectFile('latest.csv', latest.promise);
    expect(importButton()).toBeDisabled();
    expect(within(screen.getByRole('dialog')).getByRole('status')).toHaveTextContent('Reading CSV');
    fireEvent.click(importButton());
    expect(api).not.toHaveBeenCalled();
    await act(async () => latest.resolve(csv));
    expect(screen.getByLabelText('CSV text')).toHaveValue(csv);
    expect(importButton()).toBeEnabled();
    await act(async () => old.resolve('old content'));
    expect(screen.getByLabelText('CSV text')).toHaveValue(csv);
  });

  it('keeps manual text edits when a pending read finishes or fails', async () => {
    setup();
    const old = deferred<string>();
    selectFile('old.csv', old.promise);
    fireEvent.change(screen.getByLabelText('CSV text'), { target: { value: csv } });
    expect(importButton()).toBeEnabled();
    await act(async () => old.resolve('old content'));
    expect(screen.getByLabelText('CSV text')).toHaveValue(csv);
    const failing = deferred<string>();
    selectFile('failing.csv', failing.promise);
    fireEvent.change(screen.getByLabelText('CSV text'), { target: { value: csv } });
    await act(async () => failing.reject(new Error('stale read')));
    expect(within(screen.getByRole('dialog')).queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByLabelText('CSV text')).toHaveValue(csv);
  });

  it('surfaces file read failures and allows rereading the same file', async () => {
    setup();
    const failed = deferred<string>();
    selectFile('roster.csv', failed.promise);
    await act(async () => failed.reject(new Error('disk error')));
    expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent('Could not read CSV file: disk error');
    expect(within(screen.getByRole('dialog')).queryByRole('status')).not.toBeInTheDocument();
    expect(importButton()).toBeDisabled();
    const retry = deferred<string>();
    selectFile('roster.csv', retry.promise);
    expect(within(screen.getByRole('dialog')).queryByRole('alert')).not.toBeInTheDocument();
    await act(async () => retry.resolve(csv));
    expect(importButton()).toBeEnabled();
  });

  it('discards file reads across unmount and leaves a reopened dialog untouched', async () => {
    const old = deferred<string>();
    const { unmount } = setup();
    selectFile('old.csv', old.promise);
    unmount();
    setup();
    fireEvent.change(screen.getByLabelText('CSV text'), { target: { value: csv } });
    await act(async () => old.resolve('stale file'));
    expect(screen.getByLabelText('CSV text')).toHaveValue(csv);
    expect(within(screen.getByRole('dialog')).queryByRole('status')).not.toBeInTheDocument();
    expect(api).not.toHaveBeenCalled();
  });

  it('clears settled results and errors when any draft field changes', async () => {
    vi.mocked(api).mockResolvedValueOnce({ created: 1, skipped: ['Ben skipped'] }).mockRejectedValueOnce(new Error('Bad CSV'));
    const { user } = setup();
    fireEvent.change(screen.getByLabelText('CSV text'), { target: { value: csv } });
    await user.click(importButton());
    expect(await within(screen.getByRole('dialog')).findByRole('status')).toHaveTextContent('Ben skipped');
    await user.selectOptions(screen.getByLabelText('Section'), 'two');
    expect(within(screen.getByRole('dialog')).queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    await user.click(importButton());
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Bad CSV');
    fireEvent.change(screen.getByLabelText('CSV text'), { target: { value: `${csv}\nBen,10` } });
    expect(within(screen.getByRole('dialog')).queryByRole('alert')).not.toBeInTheDocument();
  });
});
