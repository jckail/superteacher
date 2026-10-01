export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

/** AuthGate listens for this to show the login screen when a session expires. */
export const UNAUTHORIZED_EVENT = 'st:unauthorized';

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    // X-Requested-With is the CSRF guard: browsers won't send a custom header cross-site without a CORS preflight.
    headers: { 'X-Requested-With': 'superteacher', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (!res.ok) {
    const d = data?.detail;
    throw new ApiError(res.status, typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e.msg).join('; ') : 'Request failed');
  }
  return data;
}

export const fmt = (v, suffix = '') => (v == null ? '—' : `${Math.round(v)}${suffix}`);
export const RISK_LABEL = { on_track: 'On track', watch: 'Watch', at_risk: 'At risk' };
