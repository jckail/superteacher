import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { AuthGate } from '../auth';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { ThemeProvider } from '../theme';
import { BANNER_STORE } from '../api';
import Login from '../pages/Login';
import EmailLogin from '../pages/EmailLogin';

const fetchMock = vi.fn();
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockRejectedValue(new Error('Offline')); });
afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, '', '/'); });

describe('public demo terms and privacy', () => {
  it('is readable while signed out and offline without requesting private data', async () => {
    window.history.replaceState(null, '', '/demo-notice');
    const previousTitle = document.title;
    const view = render(<AuthGate><p>Private classroom</p></AuthGate>);
    const heading = await screen.findByRole('heading', { name: 'Demo terms and privacy', level: 1 });
    expect(heading).toHaveFocus();
    expect(document.title).toBe('Demo terms and privacy · Super Teacher');
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText('Private classroom')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Super Teacher' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('heading', { name: 'Use synthetic data only' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What is stored' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What goes to AI' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Export and deletion' })).toBeInTheDocument();
    view.unmount();
    expect(document.title).toBe(previousTitle);
  });

  it('shows the notice instead of an existing authenticated classroom', async () => {
    window.history.replaceState(null, '', '/demo-notice');
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ authenticated: true, auth_required: true }) });
    render(<AuthGate><p>Private classroom</p></AuthGate>);
    expect(await screen.findByRole('heading', { name: 'Demo terms and privacy' })).toBeInTheDocument();
    expect(screen.queryByText('Private classroom')).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['/demo-notice-extra', '/demo-notice/private'])('does not bypass authentication on %s', async (path) => {
    window.history.replaceState(null, '', path);
    fetchMock.mockImplementation(async (url: string) => ({ ok: url === '/api/auth/config', status: url === '/api/auth/config' ? 200 : 401, json: async () => url === '/api/auth/config' ? { auth_mode: 'passcode' } : { detail: 'Unauthorized' } }));
    render(<AuthGate><p>Private classroom</p></AuthGate>);
    expect(await screen.findByLabelText('Passcode')).toBeInTheDocument();
    expect(screen.queryByText('Private classroom')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Demo terms and privacy' })).not.toBeInTheDocument();
  });

  it('keeps the workspace footer link after the demo banner is dismissed', async () => {
    sessionStorage.setItem(BANNER_STORE, '1');
    fetchMock.mockImplementation(async (url: string) => ({ ok: true, status: 200, json: async () => url === '/api/auth/config' ? { auth_mode: 'accounts' } : url === '/api/auth/me' ? { authenticated: true, auth_required: true, email: 'teacher@example.com' } : [] }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={client}><ThemeProvider><AuthGate><MemoryRouter initialEntries={['/not-a-page']}><App /></MemoryRouter></AuthGate></ThemeProvider></QueryClientProvider>);
    const link = await screen.findByRole('link', { name: /Demo terms and privacy/ });
    expect(link).toHaveAttribute('href', '/demo-notice');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByRole('button', { name: 'Dismiss demo notice' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    view.unmount();
    client.clear();
  });

  it('links the notice before entering a shared passcode', () => {
    render(<Login onSuccess={() => {}} />);
    expect(screen.getByRole('link', { name: /Demo terms and privacy/ })).toHaveAttribute('href', '/demo-notice');
  });

  it('keeps the notice available before and after requesting an email link', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 202, json: async () => ({ status: 'ok' }) });
    const user = userEvent.setup();
    render(<EmailLogin />);
    expect(screen.getByRole('link', { name: /Demo terms and privacy/ })).toHaveAttribute('href', '/demo-notice');
    await user.type(screen.getByLabelText('Email address'), 'teacher@example.com');
    await user.click(screen.getByRole('button', { name: 'Email me a sign-in link' }));
    await screen.findByRole('heading', { name: 'Check your email' });
    expect(screen.getByRole('link', { name: /Demo terms and privacy/ })).toHaveAttribute('href', '/demo-notice');
  });
});
