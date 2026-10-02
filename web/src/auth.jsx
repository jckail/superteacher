import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, UNAUTHORIZED_EVENT } from './api';
import Login from './pages/Login';
import EmailLogin from './pages/EmailLogin';
import VerifyEmail from './pages/VerifyEmail';
import './login.css';

const AuthContext = createContext({ authRequired: false, mode: 'passcode', email: null, logout: () => {}, logoutAll: () => {}, accountDeleted: () => {} });
/** `const { authRequired, mode, email, logout, logoutAll } = useAuth()` — lets any component add account controls. */
export const useAuth = () => useContext(AuthContext);

const isVerifyPage = () => window.location.pathname === '/auth/verify';

/** Renders children only for an authenticated session; otherwise the passcode or email sign-in page. */
export function AuthGate({ children, onLogout }) {
  const [state, setState] = useState({ status: 'loading', authRequired: true, mode: 'passcode', email: null, error: null });

  const check = useCallback(async () => {
    // The sign-in screen differs by mode and must render before any session exists, so ask the public config first.
    let mode = 'passcode';
    try { mode = (await api('/auth/config')).auth_mode === 'accounts' ? 'accounts' : 'passcode'; } catch { /* older server: passcode */ }
    try {
      const me = await api('/auth/me');
      setState({ status: 'in', authRequired: me.auth_required, mode, email: me.email ?? null, error: null });
    } catch (e) {
      if (e.status === 401) setState({ status: 'out', authRequired: true, mode, email: null, error: null });
      else setState({ status: 'error', authRequired: true, mode, email: null, error: e.message || 'Cannot reach the server' });
    }
  }, []);

  useEffect(() => { if (!isVerifyPage()) check(); }, [check]);
  useEffect(() => {
    const out = () => setState((s) => (s.status === 'in' ? { ...s, status: 'out', email: null } : s));
    window.addEventListener(UNAUTHORIZED_EVENT, out);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, out);
  }, []);

  const signedOut = useCallback(() => {
    onLogout?.();  // clears the React Query cache and the chat history (F-16)
    setState((s) => ({ ...s, status: 'out', email: null, error: null }));
  }, [onLogout]);
  const logout = useCallback(async () => {
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* cookie may already be gone */ }
    signedOut();
  }, [signedOut]);
  const logoutAll = useCallback(async () => {
    try { await api('/auth/logout-all', { method: 'POST' }); } catch { /* already signed out */ }
    signedOut();
  }, [signedOut]);

  if (isVerifyPage()) return <VerifyEmail />;
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
  if (state.status === 'out') {
    return state.mode === 'accounts' ? <EmailLogin /> : <Login onSuccess={() => { onLogout?.(); check(); }} />;
  }
  return (
    <AuthContext.Provider value={{ authRequired: state.authRequired, mode: state.mode, email: state.email, logout, logoutAll, accountDeleted: signedOut }}>
      {children}
    </AuthContext.Provider>
  );
}
