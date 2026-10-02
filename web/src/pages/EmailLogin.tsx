import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, api } from '../api';
import DemoNoticeLink from '../components/DemoNoticeLink';
import '../login.css';

const COOLDOWN = 60;

/** Accounts mode: ask for an email, then show a "check your email" state with a rate-limit-aware resend. */
export default function EmailLogin() {
  const [email, setEmail] = useState('');
  const [sentTo, setSentTo] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [wait, setWait] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (wait <= 0) return undefined;
    const t = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(t);
  }, [wait]);
  useEffect(() => { if (sentTo) heading.current?.focus(); }, [sentTo]);

  const pending = useRef(false);
  const request = async (address: string) => {
    if (pending.current || !address) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await api('/auth/request-link', { method: 'POST', body: { email: address } });
      setSentTo(address);
      setWait(COOLDOWN);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? 'Too many requests from this network. Please wait a few minutes and try again.' : err instanceof Error ? err.message : 'Could not send a sign-in link. Please try again.');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };

  const submit = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); request(email.trim()); };

  if (sentTo) {
    return (
      <main className="login-wrap">
        <div className="card login-card">
          <div className="brand"><span className="brand-mark" aria-hidden>🦸</span> Super Teacher</div>
          <h1 tabIndex={-1} ref={heading}>Check your email</h1>
          <p role="status" style={{ margin: 0 }}>
            If <strong>{sentTo}</strong> can receive mail, a sign-in link is on its way. It works once and expires in 15 minutes.
          </p>
          <p className="muted" style={{ margin: 0 }}>Nothing arrived? Check spam, or send another link.</p>
          {error && <div className="error" role="alert">{error}</div>}
          <button type="button" className="btn" disabled={busy || wait > 0} onClick={() => request(sentTo)}>
            {busy ? 'Sending…' : wait > 0 ? `Send again in ${wait}s` : 'Send the link again'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => { setSentTo(''); setError(''); }}>Use a different email</button>
          <DemoNoticeLink />
        </div>
      </main>
    );
  }

  return (
    <main className="login-wrap">
      <div className="card login-card">
        <div className="brand"><span className="brand-mark" aria-hidden>🦸</span> Super Teacher</div>
        <h1>Sign in</h1>
        <p className="muted" style={{ margin: 0 }}>
          Enter your email and we&apos;ll send a one-time sign-in link. No password needed.
        </p>
        <p className="demo-note" style={{ margin: 0 }}>
          This is a demo with <strong>synthetic data only</strong>. Don&apos;t enter real student information.
        </p>
        <form onSubmit={submit}>
          <label>
            Email address
            <input className="input" type="email" name="email" autoComplete="email" autoFocus required disabled={busy} maxLength={254}
              value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          {error && <div className="error" role="alert">{error}</div>}
          <button className="btn primary" type="submit" disabled={busy || !email.trim()}>{busy ? 'Sending…' : 'Email me a sign-in link'}</button>
        </form>
        <DemoNoticeLink />
      </div>
    </main>
  );
}
