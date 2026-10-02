import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { AuthMe } from './types';
import { ApiError, api, advanceApiSession, UNAUTHORIZED_EVENT } from './api';
import Login from './pages/Login';
import './login.css';

const AuthContext = createContext({ authRequired: false, logout: () => {} });
/** `const { authRequired, logout } = useAuth()` — lets any component add a sign-out button. */
export const useAuth = () => useContext(AuthContext);

export function clearPrivateSession(client: QueryClient) {
  client.clear();
  try { sessionStorage.removeItem('st-chat'); } catch { /* unavailable storage */ }
}

/** Renders children only for an authenticated session; otherwise the login page. */
export function AuthGate({ children, onLogout }: { children: ReactNode; onLogout?: () => void }) {
  const [state, setState] = useState<{ status: 'loading' | 'signing-out' | 'in' | 'out' | 'error'; authRequired: boolean; error: string | null }>({ status: 'loading', authRequired: true, error: null });

  const generation = useRef(0);
  const logoutInFlight = useRef(false);
  const clearSession = useCallback(() => {
    generation.current += 1;
    advanceApiSession();
    onLogout?.();
    setState({ status: 'out', authRequired: true, error: null });
  }, [onLogout]);

  const check = useCallback(async () => {
    const current = ++generation.current;
    advanceApiSession();
    try {
      const me = await api<AuthMe>('/auth/me');
      if (current !== generation.current) return;
      setState({ status: 'in', authRequired: me.auth_required, error: null });
    } catch (e) {
      if (current !== generation.current) return;
      if (e instanceof ApiError && e.status === 401) clearSession();
      else setState({ status: 'error', authRequired: true, error: e instanceof Error ? e.message : 'Cannot reach the server' });
    }
  }, [clearSession]);

  useEffect(() => {
    void check();
    return () => { generation.current += 1; };
  }, [check]);
  useEffect(() => {
    const out = () => { if (!logoutInFlight.current) clearSession(); };
    window.addEventListener(UNAUTHORIZED_EVENT, out);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, out);
  }, [clearSession]);

  const logout = useCallback(async () => {
    logoutInFlight.current = true;
    clearSession();
    const current = generation.current;
    setState({ status: 'signing-out', authRequired: true, error: null });
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* cookie may already be gone */ }
    logoutInFlight.current = false;
    if (current === generation.current) setState({ status: 'out', authRequired: true, error: null });
  }, [clearSession]);

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
  if (state.status === 'out') return <Login onSuccess={() => { onLogout?.(); check(); }} />;
  return (
    <AuthContext.Provider value={{ authRequired: state.authRequired, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
