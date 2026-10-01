import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, fmt } from '../api';

const respond = (status, body) => vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
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
    const [, init] = fetch.mock.calls[0];
    expect(init.body).toBe('{"a":1}');
    expect(init.headers['Content-Type']).toBe('application/json');
  });

  it('returns null for 204', async () => {
    respond(204);
    await expect(api('/x', { method: 'DELETE' })).resolves.toBeNull();
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
