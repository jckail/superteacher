import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import EmailLogin from '../pages/EmailLogin';
import VerifyEmail from '../pages/VerifyEmail';
import DemoBanner from '../components/DemoBanner';
import { ApiError, CHAT_STORE, clearSessionPrivacy } from '../api';

const json = (status, body) => Promise.resolve({ status, ok: status < 400, json: () => Promise.resolve(body) });
let fetchMock;
beforeEach(() => { fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock); });
afterEach(() => vi.unstubAllGlobals());

describe('EmailLogin', () => {
  it('asks for an email, posts it, and shows the check-your-email state', async () => {
    fetchMock.mockReturnValue(json(202, { status: 'ok' }));
    const user = userEvent.setup();
    render(<EmailLogin />);
    expect(screen.getByText(/synthetic data only/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Email address'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: /email me a sign-in link/i }));
    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('ada@example.com');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/auth/request-link');
    expect(JSON.parse(init.body)).toEqual({ email: 'ada@example.com' });
    expect(init.headers['X-Requested-With']).toBeTruthy();  // CSRF header
    expect(screen.getByRole('button', { name: /send again in/i })).toBeDisabled();  // resend is rate-limit aware
  });

  it('shows a friendly message when the network rate limit trips', async () => {
    fetchMock.mockReturnValue(json(429, { detail: 'Too many sign-in requests. Please try again later.' }));
    const user = userEvent.setup();
    render(<EmailLogin />);
    await user.type(screen.getByLabelText('Email address'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: /email me/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/too many requests/i);
  });
});

describe('VerifyEmail', () => {
  beforeEach(() => { window.history.pushState({}, '', '/auth/verify#token=abc123abc123abc123'); });

  it('reads the fragment once, strips it from the URL, and posts it', async () => {
    fetchMock.mockReturnValue(json(200, { authenticated: true }));
    const replace = vi.fn();
    const strip = vi.spyOn(window.history, 'replaceState');
    vi.stubGlobal('location', { ...window.location, hash: window.location.hash, pathname: '/auth/verify', replace });
    sessionStorage.setItem(CHAT_STORE, '[]');
    render(<VerifyEmail />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ token: 'abc123abc123abc123' });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/verify');
    expect(strip).toHaveBeenCalledWith(null, '', '/auth/verify');  // the token is gone from the address bar/history
    expect(sessionStorage.getItem(CHAT_STORE)).toBeNull();  // a previous person's chat never carries over
  });

  it('reports an invalid link and offers a new one without redirecting', async () => {
    fetchMock.mockReturnValue(json(400, { detail: 'This sign-in link is invalid or has expired. Request a new one.' }));
    window.history.pushState({}, '', '/auth/verify#token=zzzzzzzzzzzzzzzzzzzz');
    render(<VerifyEmail />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or has expired/i);
    expect(screen.getByRole('link', { name: /request a new link/i })).toHaveAttribute('href', '/');
  });

  it('does not call the API without a token', async () => {
    window.history.pushState({}, '', '/auth/verify');
    render(<VerifyEmail />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/incomplete/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('DemoBanner', () => {
  it('shows the notice and stays dismissed for the session', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<DemoBanner />);
    expect(screen.getByRole('note')).toHaveTextContent(/synthetic data only/i);
    await user.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(screen.queryByRole('note')).toBeNull();
    unmount();
    render(<DemoBanner />);
    expect(screen.queryByRole('note')).toBeNull();
  });
});

describe('quota errors and privacy', () => {
  it('surfaces the server message and flags quota 429s', async () => {
    const { api } = await import('../api');
    fetchMock.mockReturnValue(json(429, { detail: { code: 'quota_exceeded', message: "You've used today's 20 parent drafts.", resets_at: 'x' } }));
    const err = await api('/reports/students/s/parent-update', { method: 'POST', body: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.isQuota).toBe(true);
    expect(err.message).toMatch(/parent drafts/);
  });

  it('clearSessionPrivacy removes the stored chat', () => {
    sessionStorage.setItem(CHAT_STORE, '[{"role":"user","text":"hi"}]');
    clearSessionPrivacy();
    expect(sessionStorage.getItem(CHAT_STORE)).toBeNull();
  });
});
