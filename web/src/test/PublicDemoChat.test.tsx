import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Chat from '../components/Chat';

vi.mock('../auth', () => ({ useAuth: () => ({ mode: 'public_demo' }) }));
let sockets: FakeWS[];
class FakeWS {
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor() { sockets.push(this); }
  send(value: string) { this.sent.push(value); }
  close() { this.readyState = 3; }
  emit(value: unknown) { act(() => this.onmessage?.({ data: JSON.stringify(value) })); }
}
const budget = (remaining: number) => ({ used: 5-remaining, limit: 5, remaining, resets_at: '2026-10-08T00:00:00Z' });
beforeEach(() => { sockets = []; vi.stubGlobal('WebSocket', FakeWS); sessionStorage.clear(); });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('uses the server allowance and New chat cannot restore exhausted turns', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(budget(1)), { status: 200 })));
  const user = userEvent.setup();
  render(<Chat onClose={() => {}} />);
  expect(await screen.findByText(/1 of 5 assistant turns/)).toBeInTheDocument();
  await user.type(screen.getByLabelText('Message'), 'Synthetic question');
  await user.click(screen.getByRole('button', { name: 'Send' }));
  sockets[0].emit({ type: 'quota', ...budget(0) });
  sockets[0].emit({ type: 'delta', text: 'Useful response' });
  sockets[0].emit({ type: 'done' });
  expect(screen.getByText('Useful response')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'New chat' }));
  expect(screen.getByLabelText('Message')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(screen.getByText(/Daily demo limit reached/)).toBeInTheDocument();
});

it('blocks spending until a valid allowance loads and offers retry after failure', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(new Response(JSON.stringify(budget(5)), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  const user = userEvent.setup();
  render(<Chat onClose={() => {}} />);
  expect(screen.getByLabelText('Message')).toBeDisabled();
  await user.click(await screen.findByRole('button', { name: 'Retry' }));
  expect(await screen.findByText(/5 of 5 assistant turns/)).toBeInTheDocument();
  expect(screen.getByLabelText('Message')).toBeEnabled();
  expect(sockets).toHaveLength(0);
});
