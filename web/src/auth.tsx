import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { AuthConfig, AuthMe, AuthMode } from './types';
import { ApiError, api, advanceApiSession, clearSessionPrivacy, UNAUTHORIZED_EVENT } from './api';
import Login from './pages/Login';
import EmailLogin from './pages/EmailLogin';
import VerifyEmail from './pages/VerifyEmail';
import './login.css';

interface AuthContextValue { authRequired: boolean; mode: AuthMode; email: string | null; logout: () => void; logoutAll: () => void; accountDeleted: () => void }
const AuthContext = createContext<AuthContextValue>({ authRequired: false, mode: 'passcode', email: null, logout: () => {}, logoutAll: () => {}, accountDeleted: () => {} });
/** `const { authRequired, logout } = useAuth()` — lets any component add a sign-out button. */
export const useAuth = () => useContext(AuthContext);

export function clearPrivateSession(client: QueryClient) {
  client.clear();
  clearSessionPrivacy();
}

/** Renders children only for an authenticated session; otherwise the login page. */
export function AuthGate({ children, onLogout }: { children: ReactNode; onLogout?: () => void }) {
  const [state, setState] = useState<{ status: 'loading' | 'signing-out' | 'in' | 'out' | 'error'; authRequired: boolean; mode: AuthMode; email: string | null; error: string | null }>({ status: 'loading', authRequired: true, mode: 'passcode', email: null, error: null });

  const generation = useRef(0);
  const logoutInFlight = useRef(false);
  const clearSession = useCallback(() => {
    generation.current += 1;
    advanceApiSession();
    onLogout?.();
    setState((previous) => ({ ...previous, status: 'out', authRequired: true, email: null, error: null }));
  }, [onLogout]);

  const check = useCallback(async () => {
    const current = ++generation.current;
    advanceApiSession();
    let mode: AuthMode = 'passcode';
    try {
      try { mode = (await api<AuthConfig>('/auth/config')).auth_mode === 'accounts' ? 'accounts' : 'passcode'; }
      catch (error) { if (!(error instanceof ApiError && error.status === 404)) throw error; /* legacy servers expose only /auth/me */ }
      if (current !== generation.current) return;
      const me = await api<AuthMe>('/auth/me');
      if (current !== generation.current) return;
      setState({ status: 'in', authRequired: me.auth_required, mode, email: me.email ?? null, error: null });
    } catch (e) {
      if (current !== generation.current) return;
      if (e instanceof ApiError && e.status === 401) { clearSession(); setState({ status: 'out', authRequired: true, mode, email: null, error: null }); }
      else setState({ status: 'error', authRequired: true, mode, email: null, error: e instanceof Error ? e.message : 'Cannot reach the server' });
    }
  }, [clearSession]);

  useEffect(() => {
    if (window.location.pathname !== '/auth/verify') void check();
    return () => { generation.current += 1; };
  }, [check]);
  useEffect(() => {
    const out = () => { if (!logoutInFlight.current) clearSession(); };
    window.addEventListener(UNAUTHORIZED_EVENT, out);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, out);
  }, [clearSession]);

  const signOut = useCallback(async (path: '/auth/logout' | '/auth/logout-all') => {
    if (logoutInFlight.current) return;
    logoutInFlight.current = true;
    clearSession();
    const current = generation.current;
    setState((previous) => ({ ...previous, status: 'signing-out', authRequired: true, email: null, error: null }));
    try { await api(path, { method: 'POST' }); } catch { /* cookie may already be gone */ }
    logoutInFlight.current = false;
    if (current === generation.current) setState((previous) => ({ ...previous, status: 'out', authRequired: true, email: null, error: null }));
  }, [clearSession]);

  const logout = useCallback(() => { void signOut('/auth/logout'); }, [signOut]);
  const logoutAll = useCallback(() => { void signOut('/auth/logout-all'); }, [signOut]);
  if (window.location.pathname === '/auth/verify') return <VerifyEmail />;
  if (state.status === 'signing-out') return <div className="login-wrap" role="status">Signing out…</div>;
  if (state.status === 'loading') return <div className="login-wrap"><div className="skeleton" style={{ width: 240 }} /></div>;
  if (state.status === 'error') {
    return (
      <div className="login-wrap">
        <div className="card login-card">
          <p className="error" role="alert">{state.error}</p>
          <button className="btn" onClick={check}>Retry</button>
        </div>
      </div>
    );
  }
  if (state.status === 'out' && state.mode === 'accounts') return <EmailLogin />;
  if (state.status === 'out') return <Login onSuccess={() => { onLogout?.(); check(); }} />;
  return (
    <AuthContext.Provider value={{ authRequired: state.authRequired, mode: state.mode, email: state.email, logout, logoutAll, accountDeleted: clearSession }}>
      {children}
    </AuthContext.Provider>
  );
}
