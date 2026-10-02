import { CHAT_STORE } from '../api';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useDialogFocus } from './ui';
import Markdown, { type Components } from 'react-markdown';

interface Message { role: 'user' | 'assistant'; text: string }
interface ChatProps { studentId?: string | null; onClose: () => void }
function isMessage(value: unknown): value is Message {
  return typeof value === 'object' && value !== null && 'text' in value && typeof value.text === 'string' && 'role' in value && (value.role === 'user' || value.role === 'assistant');
}

const SUGGESTIONS = [
  'Who needs my attention this week?',
  'Which students are improving?',
  'Summarize attendance concerns',
  'Suggest a small-group plan for struggling students',
];
const STORE = CHAT_STORE;
const SAFE_URL = /^(https?:|mailto:)/i;

const loadHistory = (): Message[] => {
  try {
    const raw = sessionStorage.getItem(STORE);
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? value.filter(isMessage).filter((message) => message.text).slice(-60) : [];
  } catch { return []; }
};
const saveHistory = (messages: Message[]) => {
  try {
    const keep = messages.filter((m) => m.text);
    if (keep.length) sessionStorage.setItem(STORE, JSON.stringify(keep.slice(-60)));
    else sessionStorage.removeItem(STORE);
  } catch { /* storage unavailable */ }
};

/** Links from model output: only http(s)/mailto, always opened in a new tab without leaking the opener. */
const mdComponents: Components = {
  a: ({ href, children }) => (href && SAFE_URL.test(href)
    ? <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children}</a>
    : <span>{children}</span>),
  img: ({ alt }) => <span>{alt}</span>,
};

function CopyButton({ text }: { text: string }) {
  const [feedback, setFeedback] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; if (timer.current) clearTimeout(timer.current); };
  }, []);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); if (!mounted.current) return; setFeedback('Copied'); if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => setFeedback(''), 1500); } catch { if (mounted.current) setFeedback('Copy failed. Select and copy the message manually.'); }
  };
  return <><button type="button" className="btn small copy" onClick={copy} aria-label="Copy message">{feedback === 'Copied' ? 'Copied' : 'Copy'}</button><span className={feedback.startsWith('Copy failed') ? 'copy-feedback' : 'sr-only'} role="status">{feedback}</span></>;
}

/** Streaming assistant. The server builds the roster context; we only send the question and which student is on screen. */
export default function Chat({ studentId, onClose }: ChatProps) {
  const [overlay, setOverlay] = useState(() => window.matchMedia('(max-width: 1100px)').matches);
  const panel = useRef<HTMLElement>(null);
  const [messages, setMessages] = useState<Message[]>(loadHistory);
  const [contextReset, setContextReset] = useState(messages.length > 0);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [atBottom, setAtBottom] = useState(true);
  const ws = useRef<WebSocket | null>(null);
  const log = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const pending = useRef<string[]>([]);
  const busyRef = useRef(false);
  const stickRef = useRef(true);

  const setBusyBoth = useCallback((value: boolean) => {
    busyRef.current = value;
    setBusy(value);
    if (!value) setStatus('');
  }, []);

  // Detach callbacks before closing so replaced sockets cannot modify newer turns.
  const disconnect = useCallback(() => {
    const socket = ws.current;
    ws.current = null;
    pending.current = [];
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    }
  }, []);

  const connectionLost = useCallback(() => {
    setContextReset(true);
    if (busyRef.current) setMessages((messages) => [...messages.slice(0, -1), { role: 'assistant', text: '⚠️ Connection lost. Try again.' }]);
    disconnect();
    setBusyBoth(false);
  }, [disconnect, setBusyBoth]);

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${proto}://${location.host}/api/chat/ws`);
    ws.current = socket;
    socket.onopen = () => {
      if (ws.current !== socket) return;
      try { pending.current.splice(0).forEach((message) => socket.send(message)); }
      catch { connectionLost(); }
    };
    socket.onmessage = (event: MessageEvent<unknown>) => {
      if (ws.current !== socket || !busyRef.current || typeof event.data !== 'string') return;
      let value: unknown;
      try { value = JSON.parse(event.data); } catch { return; }
      if (typeof value !== 'object' || value === null || !('type' in value)) return;
      switch (value.type) {
        case 'delta': {
          if (!('text' in value) || typeof value.text !== 'string') return;
          const text = value.text;
          setStatus('');
          setMessages((messages) => {
            const last = messages.at(-1);
            return last?.role === 'assistant' ? [...messages.slice(0, -1), { ...last, text: last.text + text }] : messages;
          });
          break;
        }
        case 'tool':
          setStatus('name' in value && typeof value.name === 'string' && value.name ? `Looking up ${value.name.replace(/_/g, ' ')}…` : 'Looking things up…');
          break;
        case 'error': {
          const message = 'message' in value && typeof value.message === 'string' ? value.message : 'Something went wrong.';
          setMessages((messages) => [...messages.slice(0, -1), { role: 'assistant', text: `⚠️ ${message}` }]);
          setBusyBoth(false);
          break;
        }
        case 'done':
          setMessages((messages) => {
            const last = messages.at(-1);
            return last?.role === 'assistant' && !last.text ? [...messages.slice(0, -1), { ...last, text: '_No response received. Try again._' }] : messages;
          });
          setBusyBoth(false);
          break;
        default: break;
      }
    };
    socket.onclose = () => { if (ws.current === socket) connectionLost(); };
    socket.onerror = () => { if (ws.current === socket) connectionLost(); };
    return socket;
  }, [connectionLost, setBusyBoth]);

  useDialogFocus(panel, onClose, overlay, inputRef);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1100px)');
    const update = () => setOverlay(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => disconnect, [disconnect]);
  useEffect(() => { saveHistory(messages); }, [messages]);
  useEffect(() => { if (stickRef.current) log.current?.scrollTo({ top: log.current.scrollHeight }); }, [messages, status]);

  const onScroll = () => {
    const element = log.current;
    if (!element) return;
    const near = element.scrollHeight - element.scrollTop - element.clientHeight < 60;
    stickRef.current = near;
    setAtBottom(near);
  };
  const jump = () => { stickRef.current = true; setAtBottom(true); log.current?.scrollTo({ top: log.current.scrollHeight }); };

  const send = (value: string) => {
    const text = value.trim();
    if (!text || busyRef.current) return;
    const payload = JSON.stringify({ content: text, student_id: studentId ?? undefined, tool_events: true });
    setMessages((messages) => [...messages, { role: 'user', text }, { role: 'assistant', text: '' }]);
    setInput('');
    stickRef.current = true;
    setAtBottom(true);
    setBusyBoth(true);
    try {
      const socket = ws.current && ws.current.readyState < 2 ? ws.current : connect();
      if (socket.readyState === 0) pending.current.push(payload);
      else socket.send(payload);
    } catch { connectionLost(); }
  };

  // Backend cancellation is tied to disconnect; it does not accept cancel frames.
  const stop = () => {
    setContextReset(true);
    disconnect();
    setBusyBoth(false);
    setMessages((messages) => {
      const last = messages.at(-1);
      return last?.role === 'assistant' ? [...messages.slice(0, -1), { ...last, text: last.text || '_Stopped._' }] : messages;
    });
    inputRef.current?.focus();
  };
  const reset = () => {
    disconnect();
    setMessages([]);
    setContextReset(false);
    setBusyBoth(false);
    setAtBottom(true);
    stickRef.current = true;
    inputRef.current?.focus();
  };

  const content = (
    <aside id="assistant-panel" ref={panel} className="chat" tabIndex={-1} role={overlay ? 'dialog' : undefined} aria-modal={overlay ? true : undefined} aria-label="Super Teacher assistant" onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } }}>
      <header>
        <div><h2>Ask Super Teacher</h2><div className="muted" style={{ fontSize: '.85rem' }}>{studentId ? 'Focused on this student' : 'Looking at your whole roster'}</div></div>
        <div className="row">
          {messages.length > 0 && <button type="button" className="btn small" onClick={reset}>New chat</button>}
          <button type="button" className="btn small" onClick={onClose} aria-label="Close assistant">✕</button>
        </div>
      </header>
      {contextReset && <p className="muted" role="status">Earlier messages are saved for reference. The assistant has started a new conversation; include any needed details in your next question.</p>}
      <div className="log-wrap">
        <div className="log" ref={log} onScroll={onScroll} role="log" aria-live="polite" aria-busy={busy} tabIndex={0} aria-label="Conversation">
          {messages.length === 0 && (
            <>
              <p className="muted">I can see your roster, grades, attendance and notes. Ask me anything.</p>
              <div className="suggestions">{SUGGESTIONS.map((s) => <button type="button" key={s} onClick={() => send(s)}>{s}</button>)}</div>
            </>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}><span className="sr-only">{m.role === 'user' ? 'You: ' : 'Assistant: '}</span>
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
        <input ref={inputRef} className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your students…" aria-label="Message" maxLength={4000} onKeyDown={(event) => { if (event.key === 'Enter' && event.nativeEvent.isComposing) event.preventDefault(); }} />
        {busy
          ? <button type="button" className="btn" onClick={stop}>Stop</button>
          : <button className="btn primary" disabled={!input.trim()}>Send</button>}
      </form>
    </aside>
  );
  return overlay ? createPortal(content, document.body) : content;
}
