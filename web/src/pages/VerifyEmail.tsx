import { useEffect, useRef, useState } from 'react';
import { ApiError, api, advanceApiSession, clearSessionPrivacy } from '../api';
import '../login.css';

// React StrictMode runs effects twice in development; a sign-in token works once, so share one request per token.
const inflight = new Map<string, Promise<unknown>>();

/** /auth/verify#token=…  The token lives in the URL FRAGMENT (never sent to servers, proxies or logs). It is read once,
 *  removed from the address bar, POSTed, and the user lands on "/" (a fixed path: there is no redirect parameter). */
export default function VerifyEmail() {
  const [state, setState] = useState<{ status: 'working' | 'done' | 'error'; error: string }>({ status: 'working', error: '' });
  const heading = useRef<HTMLHeadingElement>(null);

  const tokenRef = useRef(new URLSearchParams(window.location.hash.slice(1)).get('token'));
  useEffect(() => {
    const token = tokenRef.current;
    let active = true;
    history.replaceState(null, '', window.location.pathname);  // drop the token from the address bar and history
    if (!token) { setState({ status: 'error', error: 'This sign-in link is incomplete. Request a new one.' }); return; }
    let p = inflight.get(token);
    if (!p) { p = api('/auth/verify', { method: 'POST', body: { token } }); inflight.set(token, p); }
    void p.then(() => {
      if (!active) return;
      advanceApiSession();
      clearSessionPrivacy();  // never inherit a previous person's chat on a shared computer
      setState({ status: 'done', error: '' });
      window.location.replace('/');
    }).catch((e: unknown) => { if (active) setState({ status: 'error', error: e instanceof ApiError && e.status === 429 ? 'Too many attempts. Wait a few minutes and try again.' : e instanceof Error ? e.message : 'Could not verify this link. Please try again.' }); }).finally(() => { inflight.delete(token); });
    return () => { active = false; };
  }, []);
  useEffect(() => { if (state.status !== 'working') heading.current?.focus(); }, [state.status]);

  return (
    <main className="login-wrap">
      <div className="card login-card" aria-live="polite">
        <div className="brand"><span className="brand-mark" aria-hidden>🦸</span> Super Teacher</div>
        {state.status === 'working' && <><h1>Signing you in…</h1><div className="skeleton" style={{ width: 200 }} /></>}
        {state.status === 'done' && <h1 tabIndex={-1} ref={heading}>Signed in. Taking you to your classroom…</h1>}
        {state.status === 'error' && (
          <>
            <h1 tabIndex={-1} ref={heading}>Couldn&apos;t sign you in</h1>
            <div className="error" role="alert">{state.error}</div>
            <a className="btn primary" href="/">Request a new link</a>
          </>
        )}
      </div>
    </main>
  );
}
