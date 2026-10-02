import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, fmt, UNAUTHORIZED_EVENT } from '../api';

const respond = (status: number, body?: unknown) => vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
  ok: status >= 200 && status < 300, status,
  json: () => (body === undefined ? Promise.reject(new Error('no body')) : Promise.resolve(body)),
})));

afterEach(() => vi.unstubAllGlobals());

describe('api', () => {
  it('returns parsed JSON and prefixes /api', async () => {
    respond(200, { ok: 1 });
    await expect(api('/x')).resolves.toEqual({ ok: 1 });
    expect(fetch).toHaveBeenCalledWith('/api/x', expect.objectContaining({ method: 'GET' }));
  });

  it('sends JSON bodies', async () => {
    respond(200, {});
    await api('/x', { method: 'POST', body: { a: 1 } });
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.body).toBe('{"a":1}');
    expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
  });

  it('returns null for 204', async () => {
    respond(204);
    await expect(api('/x', { method: 'DELETE' })).resolves.toBeNull();
  });

  it('emits an expiry event for private requests, but not authentication failures', async () => {
    respond(401, { detail: 'Unauthorized' });
    const expired = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, expired);
    try {
      await expect(api('/students')).rejects.toMatchObject({ status: 401 });
      expect(expired).toHaveBeenCalledOnce();
      await expect(api('/auth/login')).rejects.toMatchObject({ status: 401 });
      expect(expired).toHaveBeenCalledOnce();
    } finally { window.removeEventListener(UNAUTHORIZED_EVENT, expired); }
  });

  it('forwards cancellation and sends same-origin credentials with the request header', async () => {
    respond(200, []);
    const controller = new AbortController();
    await api('/students', { signal: controller.signal });
    expect(fetch).toHaveBeenCalledWith('/api/students', expect.objectContaining({
      signal: controller.signal, credentials: 'same-origin',
      headers: { 'X-Requested-With': 'superteacher' },
    }));
  });

  it('uses string detail as the error message', async () => {
    respond(404, { detail: 'Student not found' });
    await expect(api('/x')).rejects.toMatchObject({ status: 404, message: 'Student not found' });
    await expect(api('/x')).rejects.toBeInstanceOf(ApiError);
  });

  it('joins FastAPI validation errors', async () => {
    respond(422, { detail: [{ msg: 'field required' }, { msg: 'bad value' }] });
    await expect(api('/x')).rejects.toMatchObject({ status: 422, message: 'field required; bad value' });
  });

  it('falls back to a generic message when the body is not JSON', async () => {
    respond(500);
    await expect(api('/x')).rejects.toMatchObject({ status: 500, message: 'Request failed' });
  });
});

describe('fmt', () => {
  it('rounds and handles null', () => {
    expect(fmt(82.6, '%')).toBe('83%');
    expect(fmt(null)).toBe('—');
  });
});
