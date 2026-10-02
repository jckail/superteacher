import type { Risk } from './types';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly detail?: Record<string, unknown>) { super(message); this.name = 'ApiError'; }
  get isQuota() { return this.status === 429 && this.detail?.code === 'quota_exceeded'; }
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
  if (typeof detail === 'object' && detail !== null && 'message' in detail && typeof detail.message === 'string') return detail.message;
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
  if (!res.ok) {
    const detail = typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'object' && data.detail !== null && !Array.isArray(data.detail) ? data.detail as Record<string, unknown> : undefined;
    throw new ApiError(res.status, errorDetail(data), detail);
  }
  return data as T;
}
export const fmt = (v: number | null | undefined, suffix = '') => (v == null ? '—' : `${Math.round(v)}${suffix}`);
export const RISK_LABEL: Record<Risk, string> = { on_track: 'On track', watch: 'Watch', at_risk: 'At risk' };


/** Download only for the session that initiated the request. */
export async function downloadFile(path: string, filename: string) {
  const generation = sessionGeneration;
  const response = await fetch(`/api${path}`, { credentials: 'same-origin', headers: { 'X-Requested-With': 'superteacher' } });
  if (response.status === 401 && generation === sessionGeneration) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (!response.ok) throw new ApiError(response.status, 'Download failed');
  const blob = await response.blob();
  if (generation !== sessionGeneration) throw new ApiError(401, 'Your session changed. Please sign in again.');
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.append(link);
  try { link.click(); } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
}
export const CHAT_STORE = 'st-chat';
export const BANNER_STORE = 'st-demo-banner';
export function clearSessionPrivacy() {
  try { sessionStorage.removeItem(CHAT_STORE); } catch { /* storage unavailable */ }
}
