import { useAuth } from './auth';
import { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { NavLink, Route, Routes, useLocation, useMatch } from 'react-router-dom';
import { ScopeProvider } from './scope';
import ScopePicker from './components/ScopePicker';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import { ConfirmProvider } from './components/Confirm';
import { Loading } from './components/ui';

// Route-level code splitting keeps the first paint small; each page loads on demand.
const Overview = lazy(() => import('./pages/Overview'));
const Roster = lazy(() => import('./pages/Roster'));
const Student = lazy(() => import('./pages/Student'));
const Gradebook = lazy(() => import('./pages/Gradebook'));
const Attendance = lazy(() => import('./pages/Attendance'));
const Chat = lazy(() => import('./components/Chat'));
// Reports is built separately: wire it only when the page exists in this build.
const reportsLoader = Object.values(import.meta.glob('./pages/Reports.jsx'))[0];
const Reports = reportsLoader ? lazy(reportsLoader) : null;

// Kept for pages that still import it from here.
export { ScopePicker };

const NAV = [
  ['/', '🏠', 'Today'],
  ['/roster', '👥', 'Roster'],
  ['/gradebook', '📒', 'Gradebook'],
  ['/attendance', '✅', 'Attendance'],
  ...(Reports ? [['/reports', '📄', 'Reports']] : []),
];

const TITLES = { '/': 'Today', '/roster': 'Roster', '/gradebook': 'Gradebook', '/attendance': 'Attendance', '/reports': 'Reports' };

function useTheme() {
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('st-theme'); } catch { return null; } });
  useEffect(() => {
    const dark = theme ? theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    try { theme && localStorage.setItem('st-theme', theme); } catch { /* ignore */ }
  }, [theme]);
  return [document.documentElement.dataset.theme === 'dark', () => setTheme(() => (document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'))];
}

/** On navigation: update the tab title and move focus to <main> so keyboard/screen-reader users start at the new page. */
function useRouteAnnouncer(mainRef) {
  const { pathname } = useLocation();
  const first = useRef(true);
  useEffect(() => {
    document.title = `${TITLES[pathname] ?? (pathname.startsWith('/students/') ? 'Student' : 'Not found')} · Super Teacher`;
    if (first.current) { first.current = false; return; }
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo?.(0, 0);
  }, [pathname, mainRef]);
  return pathname;
}

function NotFound() {
  return <div className="card empty"><h1>Page not found</h1><p>That page doesn&apos;t exist.</p><NavLink className="btn primary" to="/">Back to Today</NavLink></div>;
}

function Shell() {
  const [chatOpen, setChatOpen] = useState(false);
  const [dark, toggleTheme] = useTheme();
  const { authRequired, logout } = useAuth();
  const studentMatch = useMatch('/students/:id');
  const main = useRef(null);
  const pathname = useRouteAnnouncer(main);
  return (
    <div className={`shell ${chatOpen ? 'chat-open' : ''}`}>
      <a href="#main" className="skip-link" onClick={(e) => { e.preventDefault(); main.current?.focus(); }}>Skip to content</a>
      <nav className="sidebar" aria-label="Main">
        <div className="brand"><span className="brand-mark" aria-hidden>🦸</span>Super Teacher</div>
        <div className="nav">
          {NAV.map(([to, icon, label]) => (
            <NavLink key={to} to={to} end={to === '/'}><span aria-hidden>{icon}</span>{label}</NavLink>
          ))}
          <button type="button" className={`nav-btn ${chatOpen ? 'active' : ''}`} aria-expanded={chatOpen} onClick={() => setChatOpen((o) => !o)}><span aria-hidden>✨</span>Ask AI</button>
        </div>
        <div className="spacer" />
        {authRequired && <button type="button" className="btn side-extra" onClick={logout}>Sign out</button>}
        <button type="button" className="btn side-extra" onClick={toggleTheme} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>{dark ? '☀️ Light' : '🌙 Dark'}</button>
      </nav>
      <main className="main" id="main" tabIndex={-1} ref={main}>
        <ErrorBoundary resetKey={pathname}>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/roster" element={<Roster />} />
              <Route path="/students/:id" element={<Student />} />
              <Route path="/gradebook" element={<Gradebook />} />
              <Route path="/attendance" element={<Attendance />} />
              {Reports && <Route path="/reports" element={<Reports />} />}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      {chatOpen && <Suspense fallback={null}><Chat studentId={studentMatch?.params.id} onClose={() => setChatOpen(false)} /></Suspense>}
    </div>
  );
}

export default function App() {
  return <ScopeProvider><ToastProvider><ConfirmProvider><Shell /></ConfirmProvider></ToastProvider></ScopeProvider>;
}
