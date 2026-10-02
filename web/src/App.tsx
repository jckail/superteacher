import type { RefObject } from 'react';
import { useAuth } from './auth';
import { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { NavLink, Route, Routes, useLocation, useMatch } from 'react-router-dom';
import { ScopeProvider } from './scope';
import { useTheme } from './theme';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import { ConfirmProvider } from './components/Confirm';
import { Loading } from './components/ui';
import AccountMenu from './components/AccountMenu';
import DemoBanner from './components/DemoBanner';

// Route-level code splitting keeps the first paint small; each page loads on demand.
const Overview = lazy(() => import('./pages/Overview'));
const Roster = lazy(() => import('./pages/Roster'));
const Student = lazy(() => import('./pages/Student'));
const Gradebook = lazy(() => import('./pages/Gradebook'));
const Attendance = lazy(() => import('./pages/Attendance'));
const Chat = lazy(() => import('./components/Chat'));
const Reports = lazy(() => import('./pages/Reports'));


const NAV = [
  ['/', '🏠', 'Today'],
  ['/roster', '👥', 'Roster'],
  ['/gradebook', '📒', 'Gradebook'],
  ['/attendance', '✅', 'Attendance'],
  ['/reports', '📄', 'Reports'],
];

const TITLES: Record<string, string> = { '/': 'Today', '/roster': 'Roster', '/gradebook': 'Gradebook', '/attendance': 'Attendance', '/reports': 'Reports' };

/** On navigation: update the tab title and move focus to <main> so keyboard/screen-reader users start at the new page. */
function useRouteAnnouncer(mainRef: RefObject<HTMLElement>) {
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
  const { authRequired, logout, mode } = useAuth();
  const studentMatch = useMatch('/students/:id');
  const main = useRef<HTMLElement>(null);
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
          <button type="button" className={`nav-btn ${chatOpen ? 'active' : ''}`} aria-expanded={chatOpen} aria-controls="assistant-panel" onClick={() => setChatOpen((o) => !o)}><span aria-hidden>✨</span>Ask AI</button>
        </div>
        <div className="spacer" />
        {mode === 'accounts' ? <AccountMenu /> : authRequired && <button type="button" className="btn side-extra" onClick={logout}>Sign out</button>}
        <button type="button" className="btn side-extra" onClick={toggleTheme} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>{dark ? '☀️ Light' : '🌙 Dark'}</button>
      </nav>
      <main className="main" id="main" tabIndex={-1} ref={main}>
        {mode === 'accounts' && <DemoBanner />}
        <ErrorBoundary resetKey={pathname}>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/roster" element={<Roster />} />
              <Route path="/students/:id" element={<Student />} />
              <Route path="/gradebook" element={<Gradebook />} />
              <Route path="/attendance" element={<Attendance />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      {chatOpen && <Suspense fallback={<div className="chat"><Loading /></div>}><Chat studentId={studentMatch?.params.id} onClose={() => setChatOpen(false)} /></Suspense>}
    </div>
  );
}

export default function App() {
  return <ScopeProvider><ToastProvider><ConfirmProvider><Shell /></ConfirmProvider></ToastProvider></ScopeProvider>;
}
