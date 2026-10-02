import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, useQueryClient } from '@tanstack/react-query';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, UNAUTHORIZED_EVENT } from '../api';
import { AuthGate, clearPrivateSession, useAuth } from '../auth';
import type { AuthMe } from '../types';
import { useTheme } from '../theme';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: request }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((success, failure) => { resolve = success; reject = failure; });
  return { promise, resolve, reject };
}
function PrivatePage() {
  const { logout } = useAuth();
  return <div>Private student data<button onClick={logout}>Sign out</button></div>;
}
function mount() {
  const client = new QueryClient();
  client.setQueryData(['students'], [{ name: 'Ada' }]);
  sessionStorage.setItem('st-chat', 'Private chat');
  const clear = vi.fn(() => clearPrivateSession(client));
  render(<AuthGate onLogout={clear}><PrivatePage /></AuthGate>);
  return { client, clear, user: userEvent.setup() };
}
function expectPrivateCacheCleared(client: QueryClient) {
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(client.getMutationCache().getAll()).toHaveLength(0);
  expect(sessionStorage.getItem('st-chat')).toBeNull();
}
let Root: typeof import('../main')['Root'];
beforeAll(async () => {
  const root = document.createElement('div');
  root.id = 'root';
  document.body.append(root);
  try { ({ Root } = await import('../main')); } finally { root.remove(); }
});
beforeEach(() => { request.mockReset(); });

describe('authentication private data lifecycle', () => {
  it('isolates a new session from late writes by requests from the expired session', async () => {
    const clients: QueryClient[] = [];
    function Probe() {
      const client = useQueryClient();
      if (!clients.includes(client)) clients.push(client);
      return <PrivatePage />;
    }
    request.mockResolvedValue({ authenticated: true, auth_required: true } satisfies AuthMe);
    render(<Root><Probe /></Root>);
    await screen.findByText('Private student data');
    const oldClient = clients[0];
    oldClient.setQueryData(['students'], ['old private data']);
    sessionStorage.setItem('st-chat', 'Old conversation');
    act(() => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
    expectPrivateCacheCleared(oldClient);
    // A mutation's completion can still write to the discarded client.
    oldClient.setQueryData(['students'], ['late private data']);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Passcode'), 'new-passcode');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    await screen.findByText('Private student data');
    const newClient = clients[clients.length - 1];
    expect(newClient).not.toBe(oldClient);
    expect(newClient.getQueryData(['students'])).toBeUndefined();
    expect(sessionStorage.getItem('st-chat')).toBeNull();
  });
  it('clears cached data and hides the private page immediately when a session expires', async () => {
    request.mockResolvedValue({ authenticated: true, auth_required: true } satisfies AuthMe);
    const { client, clear } = mount();
    await screen.findByText('Private student data');
    act(() => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByText('Private student data')).not.toBeInTheDocument();
    expect(clear).toHaveBeenCalledOnce();
    expectPrivateCacheCleared(client);
  });

  it('clears private data before a pending logout request completes, including when it fails', async () => {
    const pending = deferred<unknown>();
    request.mockImplementation((path: string) => path === '/auth/logout' ? pending.promise : Promise.resolve({ authenticated: true, auth_required: true } satisfies AuthMe));
    const { client, user } = mount();
    await user.click(await screen.findByRole('button', { name: 'Sign out' }));
    expectPrivateCacheCleared(client);
    expect(screen.queryByText('Private student data')).not.toBeInTheDocument();
    act(() => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
    expect(screen.getByRole('status')).toHaveTextContent('Signing out');
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument();
    await act(async () => pending.reject(new Error('offline')));
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('ignores an old session check completed after expiry', async () => {
    const pending = deferred<AuthMe>();
    request.mockReturnValue(pending.promise);
    const { client } = mount();
    act(() => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
    await act(async () => pending.resolve({ authenticated: true, auth_required: true }));
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByText('Private student data')).not.toBeInTheDocument();
    expectPrivateCacheCleared(client);
  });

  it('clears a stale private cache when the initial session check returns unauthorized', async () => {
    request.mockRejectedValue(new ApiError(401, 'Unauthorized'));
    const { client } = mount();
    await screen.findByRole('heading', { name: 'Sign in' });
    expectPrivateCacheCleared(client);
  });
});


it('keeps one saved theme across sign-in, shell changes, and sign-out', async () => {
  localStorage.setItem('st-theme', 'dark');
  let signedIn = false;
  request.mockImplementation(async (path: string) => {
    if (path === '/auth/login') { signedIn = true; return {}; }
    if (path === '/auth/logout') { signedIn = false; return {}; }
    if (!signedIn) throw new ApiError(401, 'Unauthorized');
    return { authenticated: true, auth_required: true } satisfies AuthMe;
  });
  function ThemeProbe() {
    const [dark, toggle] = useTheme();
    return <><PrivatePage /><button onClick={toggle}>{dark ? 'Use light' : 'Use dark'}</button></>;
  }
  render(<Root><ThemeProbe /></Root>);
  const user = userEvent.setup();
  await screen.findByRole('heading', { name: 'Sign in' });
  expect(document.documentElement.dataset.theme).toBe('dark');
  await user.type(screen.getByLabelText('Passcode'), 'passcode');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  await user.click(await screen.findByRole('button', { name: 'Use light' }));
  expect(document.documentElement.dataset.theme).toBe('light');
  await user.click(screen.getByRole('button', { name: 'Sign out' }));
  await screen.findByRole('heading', { name: 'Sign in' });
  expect(document.documentElement.dataset.theme).toBe('light');
  expect(localStorage.getItem('st-theme')).toBe('light');
});
