import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, UNAUTHORIZED_EVENT } from './api';
import Login from './pages/Login';
import './login.css';

const AuthContext = createContext({ authRequired: false, logout: () => {} });
/** `const { authRequired, logout } = useAuth()` — lets any component add a sign-out button. */
export const useAuth = () => useContext(AuthContext);

/** Renders children only for an authenticated session; otherwise the login page. */
export function AuthGate({ children, onLogout }) {
  const [state, setState] = useState({ status: 'loading', authRequired: true, error: null });

  const check = useCallback(async () => {
    try {
      const me = await api('/auth/me');
      setState({ status: 'in', authRequired: me.auth_required, error: null });
    } catch (e) {
      if (e.status === 401) setState({ status: 'out', authRequired: true, error: null });
      else setState({ status: 'error', authRequired: true, error: e.message || 'Cannot reach the server' });
    }
  }, []);

  useEffect(() => { check(); }, [check]);
  useEffect(() => {
    const out = () => setState((s) => (s.status === 'in' ? { ...s, status: 'out' } : s));
    window.addEventListener(UNAUTHORIZED_EVENT, out);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, out);
  }, []);

  const logout = useCallback(async () => {
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* cookie may already be gone */ }
    onLogout?.();
    setState({ status: 'out', authRequired: true, error: null });
  }, [onLogout]);

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
