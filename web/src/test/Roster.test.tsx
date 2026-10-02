import { StrictMode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', async (orig) => ({ ...(await orig<typeof import('../api')>()), api: vi.fn() }));
const scope = vi.hoisted(() => ({ course: null as { id: string } | null, section: null as { id: string } | null }));
vi.mock('../scope', () => ({ useScope: () => ({ ready: true, courses: [{ id: 'algebra', name: 'Algebra', sections: [{ id: 'p1', name: 'P1', course_id: 'algebra' }] }], ...scope, sections: [], allSections: [{ id: 'p1', name: 'P1', course_id: 'algebra', course: 'Algebra' }], setCourse() {}, setSection() {} }) }));

import type { Risk, StudentPage, StudentSummary } from '../types';
import { ApiError, api } from '../api';
import Roster from '../pages/Roster';
import { ToastProvider } from '../components/Toast';

const S = (id: string, name: string, risk: Risk = 'on_track', average: number | null = 80): StudentSummary => ({ id, name, risk, average, letter: 'B', grade_level: 9, course_id: 'algebra', section_id: 'p1', course: 'Algebra', section: 'P1', gpa: null, missing: 0, risk_reasons: [], trend: 0, attendance_rate: 95, homework_rate: 90 });
const first = Array.from({ length: 50 }, (_, i) => S(String(i), `Student ${String(i).padStart(3, '0')}`));
const middle = Array.from({ length: 50 }, (_, i) => S(String(i + 50), `Student ${i + 50}`));
const envelope = (items: StudentSummary[], next_cursor: string | null = null, total_matches = items.length, total_scoped = total_matches): StudentPage => ({ items, next_cursor, as_of: '2026-10-02', total_matches, total_scoped });
const Loc = () => { const l = useLocation(); const nav = useNavigate(); return <><output data-testid="loc">{l.search}</output><button onClick={() => nav('/roster?status=watch&q=shared')}>Shared filters</button><button onClick={() => nav(-1)}>Browser back</button><button onClick={() => nav('/roster?q=Ben&page=20')}>Legacy link</button></>; };
function setup(url = '/roster', strict = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => <QueryClientProvider client={client}><ToastProvider><MemoryRouter initialEntries={[url]}><Roster /><Loc /></MemoryRouter></ToastProvider></QueryClientProvider>;
  const view = render(strict ? <StrictMode>{tree()}</StrictMode> : tree());
  return { ...view, client, rerenderScope: () => view.rerender(tree()), user: userEvent.setup() };
}
const names = () => screen.getAllByRole('row').slice(1).map((r) => within(r).queryByRole('link')?.textContent).filter(Boolean);
function deferred<T>() { let resolve!: (v: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function request(index: number) { const [path, options] = vi.mocked(api).mock.calls[index]; return { url: new URL(path, 'https://test.invalid'), options }; }
beforeEach(() => { scope.course = null; scope.section = null; vi.mocked(api).mockReset(); vi.mocked(api).mockResolvedValue(envelope([S('2', 'Ben', 'at_risk', 0), S('4', 'Dee', 'unknown', null)])); });

describe('server-paged roster', () => {
  it('renders server order, exact totals, zero and unknown with real links', async () => {
    vi.mocked(api).mockResolvedValue(envelope([S('1', 'Zulu'), S('2', 'Alpha', 'unknown', null)], null, 2, 500));
    setup();
    await screen.findByText('Zulu');
    expect(names()).toEqual(['Zulu', 'Alpha']);
    expect(screen.getByText('2 of 500 students')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/students/2');
    expect(screen.getByRole('row', { name: /Alpha/ }).querySelector('.chip')).toHaveClass('unknown');
    expect(request(0).url.pathname).toBe('/students/page');
    expect(request(0).url.searchParams.get('limit')).toBe('50');
    expect(request(0).url.searchParams.get('sort')).toBe('risk');
    expect(request(0).url.searchParams.get('dir')).toBe('asc');
    expect(api).toHaveBeenCalledOnce();
  });

  it('fetches only clicked pages and refetches Previous with private cursor stack, retaining bounded rows', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'private-name-cursor-one', 101)).mockResolvedValueOnce(envelope(middle, 'private-name-cursor-two', 101)).mockResolvedValueOnce(envelope([S('100', 'Last')], null, 101)).mockResolvedValueOnce(envelope(middle, 'private-name-cursor-two', 101));
    const { user, client } = setup('/roster?sort=name');
    await screen.findByText('Student 000');
    expect(names()).toHaveLength(50);
    expect(api).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('Student 50');
    expect(request(1).options?.rosterCursor).toBe('private-name-cursor-one');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('Last');
    expect(names()).toEqual(['Last']);
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Previous page' }));
    await screen.findByText('Student 50');
    expect(request(3).options?.rosterCursor).toBe('private-name-cursor-one');
    expect(screen.getByTestId('loc')).not.toHaveTextContent('page=');
    await vi.waitFor(() => expect(client.getQueryCache().getAll().filter((q) => q.queryKey[1] === 'page')).toHaveLength(1));
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.queryKey))).not.toContain('private-name-cursor');
    expect(JSON.stringify(localStorage)).not.toContain('private-name-cursor');
    expect(JSON.stringify(sessionStorage)).not.toContain('private-name-cursor');
    expect(screen.getByTestId('loc')).not.toHaveTextContent('private-name-cursor');
  });

  it('restarts Previous to page one without retaining old calendar continuation', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'old', 51)).mockResolvedValueOnce(envelope([S('50', 'Later')], null, 51)).mockResolvedValueOnce(envelope(first, 'new', 51)).mockResolvedValueOnce(envelope([S('51', 'New later')], null, 51));
    const { user } = setup();
    await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Later');
    await user.click(screen.getByRole('button', { name: 'Previous page' })); await screen.findByText('Student 000');
    expect(request(2).options?.rosterCursor).toBeUndefined();
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('New later');
    expect(request(3).options?.rosterCursor).toBe('new');
  });

  it('restores global filters and sorting from URL and resets sorting to first page', async () => {
    const { user } = setup('/roster?status=unknown&q=de&sort=average&dir=desc');
    await screen.findByText('Dee');
    expect(request(0).url.searchParams.get('q')).toBe('de');
    expect(request(0).url.searchParams.get('risk')).toBe('unknown');
    expect(request(0).url.searchParams.get('sort')).toBe('average');
    expect(request(0).url.searchParams.get('dir')).toBe('desc');
    expect(screen.getByRole('columnheader', { name: /Average/ })).toHaveAttribute('aria-sort', 'descending');
    vi.mocked(api).mockResolvedValueOnce(envelope([S('x', 'New ordered')]));
    await user.click(screen.getByRole('button', { name: /^Average/ }));
    await screen.findByText('New ordered');
    expect(request(1).url.searchParams.get('dir')).toBe('asc');
    expect(request(1).options?.rosterCursor).toBeUndefined();
    expect(screen.getByTestId('loc')).not.toHaveTextContent('dir=desc');
  });

  it('normalizes numbered links without walking pages and gives a restart notice', async () => {
    setup('/roster?q=Ben&sort=name&page=999');
    await screen.findByText('Ben');
    expect(screen.getByText(/Roster page links now start at the first page/)).toHaveAttribute('role', 'status');
    expect(screen.getByTestId('loc')).toHaveTextContent('q=Ben');
    expect(screen.getByTestId('loc')).not.toHaveTextContent('page=');
    expect(api).toHaveBeenCalledOnce();
  });

  it('distinguishes empty scope, no matches and live continuation exhausted', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope([], null, 0, 0));
    const { unmount } = setup();
    await screen.findByText('No students yet'); unmount();
    vi.mocked(api).mockResolvedValueOnce(envelope([], null, 0, 80));
    const view = setup('/roster?q=absent');
    await screen.findByText('No students match.');
    expect(screen.queryByText('No students yet')).not.toBeInTheDocument(); view.unmount();
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'start', 51)).mockResolvedValueOnce(envelope([], null, 50));
    const { user } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('The roster changed. Restart to see the current first page.');
    expect(screen.getByRole('button', { name: 'Restart roster' })).toBeInTheDocument();
  });

  it('aborts stale filter responses and never applies stale rows or cursors', async () => {
    const old = deferred<StudentPage>();
    vi.mocked(api).mockReturnValueOnce(old.promise).mockResolvedValue(envelope([S('new', 'New match')]));
    const { user } = setup();
    await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    const signal = request(0).options?.signal;
    await user.type(screen.getByRole('searchbox'), 'new');
    await screen.findByText('New match');
    expect(signal?.aborted).toBe(true);
    await act(async () => old.resolve(envelope([S('old', 'Old private')], 'stale-token', 100)));
    expect(screen.queryByText('Old private')).not.toBeInTheDocument();
    expect(screen.getByRole('searchbox')).toHaveAttribute('maxlength', '120');
    expect(screen.getByTestId('loc')).toHaveTextContent('q=new');
    expect(request(vi.mocked(api).mock.calls.length - 1).url.searchParams.get('q')).toBe('new');
  });

  it('scope changes abort old responses and reset continuation', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'owned-old', 51));
    const { rerenderScope, user } = setup(); await screen.findByText('Student 000');
    const old = deferred<StudentPage>(); vi.mocked(api).mockReturnValueOnce(old.promise).mockResolvedValue(envelope([S('new', 'Scoped')]));
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    const signal = request(1).options?.signal;
    scope.course = { id: 'course-two' }; scope.section = { id: 'section-two' }; rerenderScope();
    await screen.findByText('Scoped');
    expect(signal?.aborted).toBe(true);
    expect(request(2).url.searchParams.get('course_id')).toBe('course-two');
    expect(request(2).url.searchParams.get('section_id')).toBe('section-two');
    expect(request(2).options?.rosterCursor).toBeUndefined();
    await act(async () => old.resolve(envelope([S('foreign-old', 'Wrong scope')])));
    expect(screen.queryByText('Wrong scope')).not.toBeInTheDocument();
  });

  it.each(['global', 'students'] as const)('restarts a chain on %s mutation invalidation', async (kind) => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'old', 51)).mockResolvedValueOnce(envelope([S('last', 'Later')], null, 51)).mockResolvedValue(envelope([S('fresh', 'After write')], 'fresh', 80));
    const { user, client } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Later');
    await act(async () => { await client.invalidateQueries(kind === 'students' ? { queryKey: ['students'] } : undefined); });
    await screen.findByText('After write');
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    const afterWrite = vi.mocked(api).mock.calls.slice(2);
    expect(afterWrite).toHaveLength(1);
    expect(afterWrite.every(([, options]) => options?.rosterCursor === undefined)).toBe(true);
  });

  it('invalid cursor has an explicit restart and does not automatically retry', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'invalid', 51)).mockRejectedValueOnce(new ApiError(400, 'Invalid continuation')).mockResolvedValueOnce(envelope([S('fresh', 'Restarted')]));
    const { user } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await screen.findByText('Invalid continuation');
    expect(screen.queryByText('Student 000')).not.toBeInTheDocument();
    expect(api).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole('button', { name: 'Restart roster' })); await screen.findByText('Restarted');
    expect(request(2).options?.rosterCursor).toBeUndefined();
  });

  it('retries a failed page with the same cursor and clears old rows while pending', async () => {
    const pending = deferred<StudentPage>();
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'retry-anchor', 51)).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(envelope([S('50', 'Retried')]));
    const { user } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.queryByText('Student 000')).not.toBeInTheDocument();
    await act(async () => pending.reject(new Error('Network failed')));
    await screen.findByText('Network failed'); await user.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByText('Retried'); expect(request(2).options?.rosterCursor).toBe('retry-anchor');
  });

  it('unmount drops private cursors/cache and late success cannot populate a reopened roster', async () => {
    const old = deferred<StudentPage>(); vi.mocked(api).mockReturnValueOnce(old.promise);
    const firstView = setup(); await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    firstView.unmount(); expect(request(0).options?.signal?.aborted).toBe(true);
    vi.mocked(api).mockResolvedValueOnce(envelope([S('fresh', 'New session')]));
    setup(); await screen.findByText('New session');
    await act(async () => old.resolve(envelope([S('old', 'Old session')], 'old-token', 90)));
    expect(screen.queryByText('Old session')).not.toBeInTheDocument();
    await vi.waitFor(() => expect(firstView.client.getQueryCache().getAll()).toHaveLength(0));
  });
  it('restores filter history while discarding page position', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'one', 51)).mockResolvedValueOnce(envelope([S('later', 'Later')], null, 51)).mockResolvedValueOnce(envelope([S('shared', 'Shared match')])).mockResolvedValueOnce(envelope(first, 'fresh', 51));
    const { user } = setup('/roster?sort=name'); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Later');
    await user.click(screen.getByRole('button', { name: 'Shared filters' })); await screen.findByText('Shared match');
    expect(request(2).url.searchParams.get('q')).toBe('shared');
    expect(request(2).url.searchParams.get('risk')).toBe('watch');
    await user.click(screen.getByRole('button', { name: 'Browser back' })); await screen.findByText('Student 000');
    expect(request(3).options?.rosterCursor).toBeUndefined();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  });

  it('cleans up safely through Strict Mode replay and still fetches the roster', async () => {
    setup('/roster', true);
    await screen.findByText('Ben');
    expect(names()).toEqual(['Ben', 'Dee']);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('invalidating a pending continuation rejects late metrics and refetches first page', async () => {
    const old = deferred<StudentPage>();
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'old', 51)).mockReturnValueOnce(old.promise).mockResolvedValue(envelope([S('fresh', 'Fresh grades')]));
    const { client, user } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await act(async () => { await client.invalidateQueries({ queryKey: ['students'] }); });
    await screen.findByText('Fresh grades');
    expect(request(1).options?.signal?.aborted).toBe(true);
    await act(async () => old.resolve(envelope([S('old', 'Stale grades')], 'bad', 51)));
    expect(screen.queryByText('Stale grades')).not.toBeInTheDocument();
    expect(request(2).options?.rosterCursor).toBeUndefined();
  });

  it('coalesces batched Next clicks instead of skipping an ordinal without a cursor', async () => {
    const pending = deferred<StudentPage>();
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'next-one', 101)).mockReturnValueOnce(pending.promise);
    setup(); await screen.findByText('Student 000');
    const next = screen.getByRole('button', { name: 'Next page' });
    act(() => { fireEvent.click(next); fireEvent.click(next); });
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    await act(async () => pending.resolve(envelope(middle, 'next-two', 101)));
    expect(await screen.findByText('Page 2 · 101 matching students')).toBeInTheDocument();
    expect(request(1).options?.rosterCursor).toBe('next-one');
  });

  it('notices a legacy page link introduced while the roster stays mounted', async () => {
    const { user } = setup(); await screen.findByText('Ben');
    await user.click(screen.getByRole('button', { name: 'Legacy link' }));
    await screen.findByText(/Roster page links now start at the first page/);
    expect(screen.getByTestId('loc')).toHaveTextContent('q=Ben');
    expect(screen.getByTestId('loc')).not.toHaveTextContent('page=');
  });

  it('coalesces batched Previous clicks to one valid visited cursor', async () => {
    const pending = deferred<StudentPage>();
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'one', 101)).mockResolvedValueOnce(envelope(middle, 'two', 101)).mockResolvedValueOnce(envelope([S('last', 'Last')], null, 101)).mockReturnValueOnce(pending.promise);
    const { user } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Student 50');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Last');
    const previous = screen.getByRole('button', { name: 'Previous page' });
    act(() => { fireEvent.click(previous); fireEvent.click(previous); });
    await act(async () => pending.resolve(envelope(middle, 'two', 101)));
    expect(await screen.findByText('Page 2 · 101 matching students')).toBeInTheDocument();
    expect(request(3).options?.rosterCursor).toBe('one');
  });

  it('successful add-student dialog restarts the mounted roster after a write', async () => {
    let pages = 0;
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === '/students') return {};
      pages += 1;
      return pages === 1 ? envelope(first, 'old', 51) : pages === 2 ? envelope([S('later', 'Later')], null, 51) : envelope([S('added', 'After creation')]);
    });
    const { user } = setup(); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Later');
    await user.click(screen.getByRole('button', { name: '+ Student' }));
    await user.type(screen.getByLabelText('Name'), 'Added student');
    await user.click(screen.getByRole('button', { name: 'Add student' }));
    await screen.findByText('After creation');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(request(3).options?.rosterCursor).toBeUndefined();
  });

  it('a legacy page link with unchanged filters restarts an already advanced roster', async () => {
    vi.mocked(api).mockResolvedValueOnce(envelope(first, 'one', 51)).mockResolvedValueOnce(envelope([S('later', 'Later')], null, 51)).mockResolvedValueOnce(envelope(first, 'fresh', 51));
    const { user } = setup('/roster?q=Ben'); await screen.findByText('Student 000');
    await user.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Later');
    await user.click(screen.getByRole('button', { name: 'Legacy link' }));
    await screen.findByText('Student 000');
    expect(request(2).options?.rosterCursor).toBeUndefined();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
  });

  it.each(['\uFEFFBen', '\uFEFF', '\u0085Ben'])('forwards raw Unicode search %j to the authoritative server', async (search) => {
    vi.mocked(api).mockImplementation(async (path) => {
      const received = new URL(path, 'https://test.invalid').searchParams.get('q');
      // This fixture models server answers for exact wire input, without a JS normalizer.
      return received === search ? envelope([S('exact', 'Exact server match')], null, 1, 500) : envelope([], null, 0, 500);
    });
    setup(`/roster?q=${encodeURIComponent(search)}`);
    expect(await screen.findByText('Exact server match')).toBeInTheDocument();
    expect(request(0).url.searchParams.get('q')).toBe(search);
    expect(screen.getByText('1 of 500 students')).toBeInTheDocument();
  });

});
