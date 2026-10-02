import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AccountMenu from '../components/AccountMenu';
import { ToastProvider } from '../components/Toast';

const { download } = vi.hoisted(() => ({ download: vi.fn() }));
vi.mock('../api', () => ({ api: vi.fn(), downloadFile: download }));
vi.mock('../auth', () => ({
  useAuth: () => ({ email: 'teacher@example.invalid', logout: vi.fn(), logoutAll: vi.fn() }),
}));

beforeEach(() => { download.mockReset(); });

describe('account export keyboard focus', () => {
  it.each(['success', 'failure'] as const)('restores focus immediately and keeps later activity on %s', async (outcome) => {
    let finish!: () => void;
    let fail!: (error: Error) => void;
    download.mockReturnValue(new Promise<void>((resolve, reject) => { finish = resolve; fail = reject; }));
    const user = userEvent.setup();
    render(<ToastProvider><AccountMenu /><button type="button">Continue teaching</button></ToastProvider>);

    const trigger = screen.getByRole('button', { name: 'teacher@example.invalid' });
    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: 'Sign out' })).toHaveFocus();
    await user.tab();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Export my data' })).toHaveFocus();
    await user.keyboard('{Enter}');

    expect(screen.queryByRole('group', { name: 'Account' })).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveFocus();
    expect(download).toHaveBeenCalledExactlyOnceWith('/account/export', 'super-teacher-export.json');

    await user.tab();
    const next = screen.getByRole('button', { name: 'Continue teaching' });
    expect(next).toHaveFocus();
    await act(async () => { if (outcome === 'success') finish(); else fail(new Error('Export interrupted')); });
    expect(next).toHaveFocus();
    expect(screen.getByRole(outcome === 'success' ? 'status' : 'alert'))
      .toHaveTextContent(outcome === 'success' ? 'Export downloaded' : 'Export interrupted');
  });
});
