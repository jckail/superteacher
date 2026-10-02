import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmProvider, useConfirm } from '../components/Confirm';
import { AttendanceHeat, Distribution, TrendChart } from '../components/charts';
import { ToastProvider, useToast } from '../components/Toast';
import { Loading, Modal } from '../components/ui';

function ConfirmHost() {
  const confirm = useConfirm();
  const [result, setResult] = useState('');
  return <><button onClick={async () => setResult(String(await confirm({ title: 'Delete note?', message: 'This will remove the note.' })))}>Delete</button><p>{result}</p></>;
}

describe('Accessible feedback and charts', () => {
  it('describes confirmation, focuses cancel and restores its invoking button', async () => {
    const user = userEvent.setup();
    render(<ConfirmProvider><ConfirmHost /></ConfirmProvider>);
    const opener = screen.getByRole('button', { name: 'Delete' });
    await user.click(opener);
    expect(screen.getByRole('alertdialog')).toHaveAccessibleDescription('This will remove the note.');
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    expect(screen.getByText('false')).toBeInTheDocument();
  });

  it('isolates the background and restores its original scroll state', () => {
    document.body.style.overflow = 'auto';
    const { container, unmount } = render(<Modal title="Edit" onClose={() => {}}><button>Save</button></Modal>);
    expect(container.inert).toBe(true);
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    expect(container.inert).toBe(false);
    expect(document.body.style.overflow).toBe('auto');
    document.body.style.overflow = '';
  });

  it('announces loading with actual text', () => {
    render(<Loading />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
  });

  it('provides daily attendance data beyond color and mouse tooltips', () => {
    render(<AttendanceHeat days={[{ day: '2026-10-02', status: 'absent' }, { day: '2026-10-01', status: 'present' }]} />);
    const table = screen.getByRole('table', { name: 'Daily attendance' });
    const rows = within(table).getAllByRole('row');
    expect(rows[1]).toHaveTextContent('2026-10-01present');
    expect(rows[2]).toHaveTextContent('2026-10-02absent');
    expect(screen.getByRole('img')).toHaveAccessibleName(/2 recorded days: 1 absent, 1 present/);
  });

  it('keeps grade distribution numbers available as a labelled table', () => {
    render(<Distribution dist={{ A: 2, F: 1 }} />);
    const table = screen.getByRole('table', { name: 'Grade distribution' });
    expect(within(table).getByRole('rowheader', { name: 'A' }).parentElement).toHaveTextContent('A2');
    expect(within(table).getByRole('columnheader', { name: 'Students' })).toBeInTheDocument();
    expect(screen.getByText('3 graded students')).toBeInTheDocument();
  });

  it('excludes invalid numeric chart points and makes detail keyboard accessible', async () => {
    const user = userEvent.setup();
    render(<TrendChart points={[{ label: 'Invalid', short: '?', pct: NaN }, { label: 'Quiz one', short: '1', pct: 70 }, { label: 'Quiz two', short: '2', pct: 90, detail: 'Improved' }]} />);
    const chart = screen.getByRole('group');
    expect(chart).toHaveAccessibleName('Score trend across 2 assignments, latest 90%');
    expect(chart.innerHTML).not.toMatch(/NaN|Infinity/);
    await user.tab();
    expect(screen.getByRole('img', { name: 'Quiz one: 70%' })).toHaveFocus();
    expect(screen.getByText('Quiz one')).toBeInTheDocument();
  });
});


it('keeps error notifications available until explicitly dismissed', () => {
  vi.useFakeTimers();
  try {
    function Notify() {
      const toast = useToast();
      return <button onClick={() => toast.error('Save failed')}>Save</button>;
    }
    render(<ToastProvider><Notify /></ToastProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    act(() => vi.advanceTimersByTime(30000));
    expect(screen.getByRole('alert')).toHaveTextContent('Save failed');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification: Save failed' }));
    expect(screen.queryByText('Save failed')).not.toBeInTheDocument();
  } finally { vi.useRealTimers(); }
});


it('restores the background when a whole nested dialog tree unmounts', async () => {
  const user = userEvent.setup();
  function Nested() {
    const [child, setChild] = useState(false);
    return <Modal title="Parent" onClose={() => {}}><button onClick={() => setChild(true)}>Nested dialog</button>{child && <Modal title="Child" onClose={() => {}}>Child content</Modal>}</Modal>;
  }
  const { container, unmount } = render(<Nested />);
  await user.click(screen.getByRole('button', { name: 'Nested dialog' }));
  expect(container.inert).toBe(true);
  unmount();
  expect(container.inert).toBe(false);
  expect(document.body.style.overflow).toBe('');
});
