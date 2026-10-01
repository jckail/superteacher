import { useCallback, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';

const SUGGESTIONS = [
  'Who needs my attention this week?',
  'Which students are improving?',
  'Summarize attendance concerns',
  'Suggest a small-group plan for struggling students',
];

/** Streaming assistant. The server builds the roster context; we only send the question and which student is on screen. */
export default function Chat({ studentId, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const ws = useRef(null);
  const log = useRef(null);
  const pending = useRef([]);
  const busyRef = useRef(false);
  const setBusyBoth = (v) => { busyRef.current = v; setBusy(v); };

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const sock = new WebSocket(`${proto}://${location.host}/api/chat/ws`);
    sock.onopen = () => { pending.current.splice(0).forEach((m) => sock.send(m)); };
    sock.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      if (ev.type === 'delta') {
        setMessages((m) => [...m.slice(0, -1), { ...m.at(-1), text: m.at(-1).text + ev.text }]);
      } else {
        if (ev.type === 'error') setMessages((m) => [...m.slice(0, -1), { role: 'assistant', text: `⚠️ ${ev.message}` }]);
        setBusyBoth(false);
      }
    };
    sock.onclose = () => {
      ws.current = null;
      if (busyRef.current) setMessages((m) => [...m.slice(0, -1), { role: 'assistant', text: '⚠️ Connection lost. Try again.' }]);
      setBusyBoth(false);
    };
    ws.current = sock;
  }, []);

  useEffect(() => { connect(); return () => ws.current?.close(); }, [connect]);
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight }); }, [messages]);

  const send = (text) => {
    text = text.trim();
    if (!text || busy) return;
    const payload = JSON.stringify({ content: text, student_id: studentId ?? undefined });
    if (!ws.current || ws.current.readyState > 1) { connect(); pending.current.push(payload); }
    else if (ws.current.readyState === 0) pending.current.push(payload);
    else ws.current.send(payload);
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '' }]);
    setInput('');
    setBusyBoth(true);
  };

  const reset = () => { ws.current?.send(JSON.stringify({ type: 'reset' })); setMessages([]); };

  return (
    <aside className="chat" aria-label="Super Teacher assistant">
      <header>
        <div><h2>Ask Super Teacher</h2><div className="muted" style={{ fontSize: '.85rem' }}>{studentId ? 'Focused on this student' : 'Looking at your whole roster'}</div></div>
        <div className="row">
          {messages.length > 0 && <button className="btn small" onClick={reset}>New chat</button>}
          <button className="btn small" onClick={onClose} aria-label="Close assistant">✕</button>
        </div>
      </header>
      <div className="log" ref={log} aria-live="polite">
        {messages.length === 0 && (
          <>
            <p className="muted">I can see your roster, grades, attendance and notes. Ask me anything.</p>
            <div className="suggestions">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>
          </>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === 'user' ? m.text : m.text ? <Markdown>{m.text}</Markdown> : <span className="typing" aria-label="Thinking" />}
          </div>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your students…" aria-label="Message" />
        <button className="btn primary" disabled={busy || !input.trim()}>Send</button>
      </form>
    </aside>
  );
}
