import type { Risk } from './types';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); this.name = 'ApiError'; }
}
export const UNAUTHORIZED_EVENT = 'st:unauthorized';
let sessionGeneration = 0;
/** Invalidate expiry notifications from requests started in an earlier session. */
export function advanceApiSession() { sessionGeneration += 1; }
export interface ApiOptions { method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'; body?: unknown; signal?: AbortSignal }

function errorDetail(data: unknown): string {
  if (typeof data !== 'object' || data === null || !('detail' in data)) return 'Request failed';
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((entry: unknown) => typeof entry === 'object' && entry !== null && 'msg' in entry && typeof entry.msg === 'string' ? [entry.msg] : []);
    if (messages.length) return messages.join('; ');
  }
  return 'Request failed';
}

/** Response types follow the server contract; callers can supply a query cancellation signal. */
export async function api<T = unknown>(path: string, { method = 'GET', body, signal }: ApiOptions = {}): Promise<T> {
  const requestGeneration = sessionGeneration;
  const res = await fetch(`/api${path}`, {
    method, signal, credentials: 'same-origin',
    headers: { 'X-Requested-With': 'superteacher', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && !path.startsWith('/auth/') && requestGeneration === sessionGeneration) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (res.status === 204) return null as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, errorDetail(data));
  return data as T;
}
export const fmt = (v: number | null | undefined, suffix = '') => (v == null ? '—' : `${Math.round(v)}${suffix}`);
export const RISK_LABEL: Record<Risk, string> = { on_track: 'On track', watch: 'Watch', at_risk: 'At risk' };
