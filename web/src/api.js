export class ApiError extends Error {
  constructor(status, message, detail) { super(message); this.status = status; this.detail = detail; }
  /** True for the server's friendly daily-limit 429 (chat messages, AI insights, parent drafts). */
  get isQuota() { return this.status === 429 && this.detail?.code === 'quota_exceeded'; }
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
    const message = typeof d === 'string' ? d
      : Array.isArray(d) ? d.map((e) => e.msg).join('; ')
      : typeof d?.message === 'string' ? d.message : 'Request failed';  // quota 429s carry {code, message, resets_at}
    throw new ApiError(res.status, message, d && typeof d === 'object' && !Array.isArray(d) ? d : undefined);
  }
  return data;
}

/** Fetch a file with the session and hand it to the browser as a download (used for the account export). */
export async function downloadFile(path, filename) {
  const res = await fetch(`/api${path}`, { credentials: 'same-origin', headers: { 'X-Requested-With': 'superteacher' } });
  if (!res.ok) throw new ApiError(res.status, 'Download failed');
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Everything that must not outlive a session on a shared computer (privacy finding F-16). */
export const CHAT_STORE = 'st-chat';
export const BANNER_STORE = 'st-demo-banner';
export function clearSessionPrivacy() {
  try { sessionStorage.removeItem(CHAT_STORE); } catch { /* storage unavailable */ }
}

export const fmt = (v, suffix = '') => (v == null ? '—' : `${Math.round(v)}${suffix}`);
export const RISK_LABEL = { on_track: 'On track', watch: 'Watch', at_risk: 'At risk' };
