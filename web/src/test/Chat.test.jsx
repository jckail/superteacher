import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Chat from '../components/Chat';

let sockets;
class FakeWS {
  static OPEN = 1;
  constructor(url) { this.url = url; this.readyState = 1; this.sent = []; sockets.push(this); queueMicrotask(() => this.onopen?.()); }
  send(m) { this.sent.push(JSON.parse(m)); }
  close() { this.readyState = 3; this.onclose?.(); }
  emit(ev) { act(() => this.onmessage({ data: JSON.stringify(ev) })); }
}

beforeEach(() => { sockets = []; vi.stubGlobal('WebSocket', FakeWS); });
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

  it('stop sends cancel and ignores late deltas', async () => {
    const { ws, user } = await ask();
    ws.emit({ type: 'delta', text: 'partial' });
    await user.click(screen.getByRole('button', { name: 'Stop' }));
    expect(ws.sent.at(-1)).toEqual({ type: 'cancel' });
    ws.emit({ type: 'delta', text: ' LATE' });
    expect(screen.queryByText(/LATE/)).toBeNull();
    ws.emit({ type: 'done' });
    expect(screen.getByText('partial')).toBeInTheDocument();
  });

  it('opens external links safely and does not render raw HTML', async () => {
    const { ws } = await ask();
    ws.emit({ type: 'delta', text: '[docs](https://example.com) <img src=x onerror=alert(1)> [bad](javascript:alert(1))' });
    const a = screen.getByRole('link', { name: 'docs' });
    expect(a).toHaveAttribute('target', '_blank');
    expect(a.getAttribute('rel')).toMatch(/noopener/);
    expect(document.querySelector('img')).toBeNull();
    expect(screen.queryByRole('link', { name: 'bad' })).toBeNull();
  });

  it('persists history per tab in sessionStorage and restores it', async () => {
    const { ws, unmount } = await ask('Remember me');
    ws.emit({ type: 'delta', text: 'Sure.' });
    ws.emit({ type: 'done' });
    unmount();
    expect(JSON.parse(sessionStorage.getItem('st-chat')).map((m) => m.text)).toEqual(['Remember me', 'Sure.']);
    render(<Chat onClose={() => {}} />);
    expect(screen.getByText('Remember me')).toBeInTheDocument();
    expect(screen.getByText('Sure.')).toBeInTheDocument();
  });

  it('reports a lost connection mid-stream', async () => {
    const { ws } = await ask();
    act(() => ws.close());
    expect(screen.getByText(/Connection lost/)).toBeInTheDocument();
  });
});
