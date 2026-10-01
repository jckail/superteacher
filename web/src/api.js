export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data?.detail;
    throw new ApiError(res.status, typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e.msg).join('; ') : 'Request failed');
  }
  return data;
}

export const fmt = (v, suffix = '') => (v == null ? '—' : `${Math.round(v)}${suffix}`);
export const RISK_LABEL = { on_track: 'On track', watch: 'Watch', at_risk: 'At risk' };
