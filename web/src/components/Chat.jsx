import { useCallback, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { CHAT_STORE } from '../api';

const SUGGESTIONS = [
  'Who needs my attention this week?',
  'Which students are improving?',
  'Summarize attendance concerns',
  'Suggest a small-group plan for struggling students',
];
const STORE = CHAT_STORE;
const SAFE_URL = /^(https?:|mailto:)/i;

const loadHistory = () => {
  try {
    const v = JSON.parse(sessionStorage.getItem(STORE));
    return Array.isArray(v) ? v.filter((m) => m && typeof m.text === 'string' && (m.role === 'user' || m.role === 'assistant')) : [];
  } catch { return []; }
};
const saveHistory = (messages) => {
  try {
    const keep = messages.filter((m, i) => m.text || i < messages.length - 1);
    keep.length ? sessionStorage.setItem(STORE, JSON.stringify(keep.slice(-60))) : sessionStorage.removeItem(STORE);
  } catch { /* storage unavailable */ }
};

/** Links from model output: only http(s)/mailto, always opened in a new tab without leaking the opener. */
const mdComponents = {
  a: ({ href, children }) => (href && SAFE_URL.test(href)
    ? <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children}</a>
    : <span>{children}</span>),
  img: ({ alt }) => <span>{alt}</span>,
};

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* clipboard blocked */ }
  };
  return <button type="button" className="btn small copy" onClick={copy} aria-label="Copy message">{done ? 'Copied' : 'Copy'}</button>;
}

/** Streaming assistant. The server builds the roster context; we only send the question and which student is on screen. */
export default function Chat({ studentId, onClose }) {
  const [messages, setMessages] = useState(loadHistory);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [stopping, setStopping] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const ws = useRef(null);
  const log = useRef(null);
  const inputRef = useRef(null);
  const pending = useRef([]);
  const busyRef = useRef(false);
  const stickRef = useRef(true);
  const ignoreDeltas = useRef(false);
  const stopTimer = useRef(null);
  const setBusyBoth = (v) => { busyRef.current = v; setBusy(v); if (!v) { setStatus(''); setStopping(false); clearTimeout(stopTimer.current); } };

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const sock = new WebSocket(`${proto}://${location.host}/api/chat/ws`);
    sock.onopen = () => { pending.current.splice(0).forEach((m) => sock.send(m)); };
    sock.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      if (!ev || typeof ev !== 'object') return;
      switch (ev.type) {
        case 'delta':
          if (ignoreDeltas.current || typeof ev.text !== 'string') return;
          setStatus('');
          setMessages((m) => (m.length ? [...m.slice(0, -1), { ...m.at(-1), text: m.at(-1).text + ev.text }] : m));
          break;
        case 'tool':
          if (!ignoreDeltas.current) setStatus(ev.name ? `Looking up ${String(ev.name).replace(/_/g, ' ')}…` : 'Looking things up…');
          break;
        case 'error':
          ignoreDeltas.current = false;
          setMessages((m) => [...m.slice(0, -1), { role: 'assistant', text: `⚠️ ${ev.message ?? 'Something went wrong.'}` }]);
          setBusyBoth(false);
          break;
        case 'done':
          ignoreDeltas.current = false;
          setBusyBoth(false);
          break;
        default: break;   // unknown event types from newer servers are ignored
      }
    };
    sock.onclose = () => {
      if (ws.current === sock) ws.current = null;
      const stopped = ignoreDeltas.current;
      ignoreDeltas.current = false;
      if (busyRef.current && !stopped) setMessages((m) => [...m.slice(0, -1), { role: 'assistant', text: '⚠️ Connection lost. Try again.' }]);
      setBusyBoth(false);
    };
    ws.current = sock;
  }, []);

  useEffect(() => { connect(); inputRef.current?.focus(); return () => { clearTimeout(stopTimer.current); const s = ws.current; ws.current = null; if (s) { s.onclose = null; s.close(); } }; }, [connect]);
  useEffect(() => { saveHistory(messages); }, [messages]);
  useEffect(() => { if (stickRef.current) log.current?.scrollTo({ top: log.current.scrollHeight }); }, [messages, status]);

  const onScroll = () => {
    const el = log.current;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    stickRef.current = near;
    setAtBottom(near);
  };
  const jump = () => { stickRef.current = true; setAtBottom(true); log.current?.scrollTo({ top: log.current.scrollHeight }); };

  const send = (text) => {
    text = text.trim();
    if (!text || busy) return;
    const payload = JSON.stringify({ content: text, student_id: studentId ?? undefined });
    if (!ws.current || ws.current.readyState > 1) { connect(); pending.current.push(payload); }
    else if (ws.current.readyState === 0) pending.current.push(payload);
    else ws.current.send(payload);
    setMessages((m) => [...m, { role: 'user', text }, { role: 'assistant', text: '' }]);
    setInput('');
    ignoreDeltas.current = false;
    stickRef.current = true;
    setBusyBoth(true);
  };

  /** Ask the server to stop; if it ignores us, drop the socket after a moment so the stream really ends. */
  const stop = () => {
    try { ws.current?.send(JSON.stringify({ type: 'cancel' })); } catch { /* socket closing */ }
    ignoreDeltas.current = true;
    setStopping(true);
    setStatus('');
    stopTimer.current = setTimeout(() => {
      if (!busyRef.current) return;
      ws.current?.close();
    }, 2000);
    setMessages((m) => (m.at(-1)?.role === 'assistant' ? [...m.slice(0, -1), { ...m.at(-1), text: m.at(-1).text || '_Stopped._' }] : m));
  };

  const reset = () => {
    try { ws.current?.send(JSON.stringify({ type: 'reset' })); } catch { /* ignore */ }
    setMessages([]);
    setBusyBoth(false);
  };

  return (
    <aside className="chat" aria-label="Super Teacher assistant">
      <header>
        <div><h2>Ask Super Teacher</h2><div className="muted" style={{ fontSize: '.85rem' }}>{studentId ? 'Focused on this student' : 'Looking at your whole roster'}</div></div>
        <div className="row">
          {messages.length > 0 && <button type="button" className="btn small" onClick={reset}>New chat</button>}
          <button type="button" className="btn small" onClick={onClose} aria-label="Close assistant">✕</button>
        </div>
      </header>
      <div className="log-wrap">
        <div className="log" ref={log} onScroll={onScroll} role="log" aria-live="polite" aria-busy={busy} tabIndex={0} aria-label="Conversation">
          {messages.length === 0 && (
            <>
              <p className="muted">I can see your roster, grades, attendance and notes. Ask me anything.</p>
              <div className="suggestions">{SUGGESTIONS.map((s) => <button type="button" key={s} onClick={() => send(s)}>{s}</button>)}</div>
            </>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === 'user' ? m.text : m.text
                ? <><Markdown skipHtml components={mdComponents}>{m.text}</Markdown>{!(busy && i === messages.length - 1) && <CopyButton text={m.text} />}</>
                : <span className="typing" role="status" aria-label="Thinking" />}
            </div>
          ))}
          {busy && status && <div className="status-line" role="status">{status}</div>}
        </div>
        {!atBottom && busy && <button type="button" className="btn small jump" onClick={jump}>↓ Latest</button>}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <input ref={inputRef} className="input" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && onClose()} placeholder="Ask about your students…" aria-label="Message" />
        {busy
          ? <button type="button" className="btn" onClick={stop} disabled={stopping}>{stopping ? 'Stopping…' : 'Stop'}</button>
          : <button className="btn primary" disabled={!input.trim()}>Send</button>}
      </form>
    </aside>
  );
}
