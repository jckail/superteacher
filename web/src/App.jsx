import { useEffect, useState } from 'react';
import { NavLink, Route, Routes, useMatch } from 'react-router-dom';
import { ScopeProvider, useScope } from './scope';
import Overview from './pages/Overview';
import Roster from './pages/Roster';
import Student from './pages/Student';
import Gradebook from './pages/Gradebook';
import Attendance from './pages/Attendance';
import Chat from './components/Chat';

const NAV = [
  ['/', '🏠', 'Today'],
  ['/roster', '👥', 'Roster'],
  ['/gradebook', '📒', 'Gradebook'],
  ['/attendance', '✅', 'Attendance'],
];

function useTheme() {
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('st-theme'); } catch { return null; } });
  useEffect(() => {
    const dark = theme ? theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    try { theme && localStorage.setItem('st-theme', theme); } catch { /* ignore */ }
  }, [theme]);
  return [document.documentElement.dataset.theme === 'dark', () => setTheme((t) => (document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'))];
}

export function ScopePicker() {
  const { courses, course, section, sections, setCourse, setSection } = useScope();
  return (
    <div className="scope">
      <select className="input compact" value={course?.id ?? ''} onChange={(e) => setCourse(e.target.value)} aria-label="Course">
        <option value="">All courses</option>
        {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <select className="input compact" value={section?.id ?? ''} onChange={(e) => setSection(e.target.value)} aria-label="Section">
        <option value="">All sections</option>
        {sections.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
    </div>
  );
}

function Shell() {
  const [chatOpen, setChatOpen] = useState(false);
  const [dark, toggleTheme] = useTheme();
  const studentMatch = useMatch('/students/:id');
  return (
    <div className={`shell ${chatOpen ? 'chat-open' : ''}`}>
      <nav className="sidebar" aria-label="Main">
        <div className="brand"><span className="brand-mark">🦸</span>Super Teacher</div>
        <div className="nav">
          {NAV.map(([to, icon, label]) => (
            <NavLink key={to} to={to} end={to === '/'}><span aria-hidden>{icon}</span>{label}</NavLink>
          ))}
          <a href="#ask" onClick={(e) => { e.preventDefault(); setChatOpen((o) => !o); }} className={chatOpen ? 'active' : ''}><span aria-hidden>✨</span>Ask AI</a>
        </div>
        <div className="spacer" />
        <button className="btn side-extra" onClick={toggleTheme}>{dark ? '☀️ Light' : '🌙 Dark'}</button>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/roster" element={<Roster />} />
          <Route path="/students/:id" element={<Student />} />
          <Route path="/gradebook" element={<Gradebook />} />
          <Route path="/attendance" element={<Attendance />} />
          <Route path="*" element={<div className="empty">Page not found.</div>} />
        </Routes>
      </main>
      {chatOpen && <Chat studentId={studentMatch?.params.id} onClose={() => setChatOpen(false)} />}
    </div>
  );
}

export default function App() {
  return <ScopeProvider><Shell /></ScopeProvider>;
}
