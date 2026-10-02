import type { FormEvent } from 'react';
import { useId, useState } from 'react';
import { api, ApiError } from '../api';
import DemoNoticeLink from '../components/DemoNoticeLink';
import '../login.css';

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const errorId = useId();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await api('/auth/login', { method: 'POST', body: { password } });
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? 'Incorrect passcode.' : err instanceof Error ? err.message : 'Unable to sign in. Please try again.');
      setBusy(false);
    }
  };

  return (
    <main className="login-wrap">
      <div className="card login-card">
        <div className="brand"><span className="brand-mark">🦸</span> Super Teacher</div>
        <h1>Sign in</h1>
        <p className="muted" style={{ margin: 0 }}>Enter the shared passcode to continue.</p>
        <form onSubmit={submit} aria-busy={busy}>
          <label>
            Passcode
            <input className="input" type="password" autoComplete="current-password" autoFocus required
              aria-describedby={error ? errorId : undefined}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <div id={errorId} className="error" role="alert">{error}</div>}
          <button className="btn primary" type="submit" disabled={busy || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
        <DemoNoticeLink />
      </div>
    </main>
  );
}
