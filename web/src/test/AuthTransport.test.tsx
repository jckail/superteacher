import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { AuthGate, useAuth } from '../auth';

function response(status: number, data: unknown = {}) {
  return { status, ok: status >= 200 && status < 300, json: async () => data } as Response;
}
afterEach(() => vi.unstubAllGlobals());

it('keeps the new login when an earlier mutation returns 401, while current expiry still signs out', async () => {
  let completeOld!: (value: Response) => void;
  const old = new Promise<Response>((resolve) => { completeOld = resolve; });
  const failed = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/assessments/old/scores') return old;
    if (url === '/api/current-private') return response(401, { detail: 'Unauthorized' });
    if (url === '/api/auth/logout') return response(204);
    if (url === '/api/auth/login') return response(200);
    if (url === '/api/auth/me') return response(200, { authenticated: true, auth_required: true });
    throw new Error(`Unexpected request ${url}`);
  }));
  function PrivatePage() {
    const { logout } = useAuth();
    return <><p>Private page</p><button onClick={() => void api('/assessments/old/scores', { method: 'PUT', body: { scores: [] } }).catch(failed)}>Save old score</button><button onClick={logout}>Sign out</button></>;
  }
  render(<AuthGate><PrivatePage /></AuthGate>);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Save old score' }));
  await user.click(screen.getByRole('button', { name: 'Sign out' }));
  await screen.findByRole('heading', { name: 'Sign in' });
  await user.type(screen.getByLabelText('Passcode'), 'new-passcode');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByText('Private page');
  await act(async () => { completeOld(response(401, { detail: 'Expired old session' })); });
  expect(failed).toHaveBeenCalledWith(expect.objectContaining({ status: 401 }));
  expect(screen.getByText('Private page')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument();
  await act(async () => { await expect(api('/current-private')).rejects.toMatchObject({ status: 401 }); });
  expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
});
