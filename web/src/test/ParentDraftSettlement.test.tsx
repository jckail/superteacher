import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import Reports from '../pages/Reports';
import { ScopeProvider } from '../scope';
import { useAuth } from '../auth';
import type { ClassSummary, CourseOut, ParentUpdateOut, StudentPage } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
vi.mock('react-dom/client', async (load) => ({ ...await load<typeof import('react-dom/client')>(), default: { createRoot: () => ({ render: vi.fn() }) } }));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const courses: CourseOut[] = [{ id: 'math', name: 'Math', sections: [{ id: 'p1', course_id: 'math', name: 'Period 1' }, { id: 'p2', course_id: 'math', name: 'Period 2' }] }];
const summary: ClassSummary = { as_of: '2026-10-02', section_id: 'p1', section: 'Period 1', course: 'Math', students: 1, unknown: 1, on_track: 0, watch: 0, at_risk: 0, average: null, distribution: { A: 0, B: 0, C: 0, D: 0, F: 0 }, assessments: [], attention: [], attendance: [], attendance_rate: null };
const students: StudentPage = { items: [{ id: 'ada', name: 'Ada', grade_level: 4, section_id: 'p1', section: 'Period 1', course_id: 'math', course: 'Math', average: null, letter: null, gpa: null, trend: null, attendance_rate: null, homework_rate: null, missing: 0, risk: 'unknown', risk_reasons: [] }], next_cursor: null, as_of: '2026-10-02', total_scoped: 1, total_matches: 1 };
const originalDraft: ParentUpdateOut = { subject: 'Original Ada subject', body: 'Original Ada message', source: 'template' };
const regeneratedDraft: ParentUpdateOut = { subject: 'New generated subject', body: 'New generated message', source: 'ai' };
function writes() { return vi.mocked(api).mock.calls.filter(([path, options]) => path.endsWith('/parent-update') && options?.method === 'POST'); }
function transport() {
  const regeneration = deferred<ParentUpdateOut>();
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/courses' && !options?.method) return courses as never;
    if (path === '/calendar' && !options?.method) return { timezone: 'America/Los_Angeles', today: '2026-10-02' } as never;
    if (/^\/reports\/sections\/p[12]\/summary$/.test(path) && !options?.method) return { ...summary, section_id: path.split('/')[3] } as never;
    if (path.startsWith('/students/page?') && !options?.method) {
      const sectionId = new URL(path, 'https://example.test').searchParams.get('section_id')!;
      const ada = { ...students.items[0], section_id: sectionId };
      return { ...students, items: [ada, { ...ada, id: 'ben', name: 'Ben' }], total_scoped: 2, total_matches: 2 } as never;
    }
    if (path === '/reports/students/ada/parent-update' && options?.method === 'POST') return (writes().length === 1 ? originalDraft : regeneration.promise) as never;
    throw new Error(`Unexpected request ${path}`);
  });
  return regeneration;
}
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><MemoryRouter><ScopeProvider><Reports /></ScopeProvider></MemoryRouter></QueryClientProvider>);
  return { ...view, client, user: userEvent.setup() };
}
async function beginRegeneration(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: 'Ada' });
  await user.selectOptions(screen.getByRole('combobox', { name: 'Student' }), 'ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  const subject = await screen.findByLabelText('Subject');
  const message = screen.getByLabelText('Message');
  expect(subject).toHaveValue(originalDraft.subject); expect(message).toHaveValue(originalDraft.body);
  expect(screen.getByText('Template draft')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Regenerate' }));
  await waitFor(() => expect(writes()).toHaveLength(2));
  expect(writes()).toEqual(Array.from({ length: 2 }, () => ['/reports/students/ada/parent-update', { method: 'POST', body: { tone: 'warm', expected_section_id: 'p1' } }]));
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  expect(subject).toBeEnabled(); expect(message).toBeEnabled();
  return { subject, message };
}
async function complete(regeneration: ReturnType<typeof transport>) {
  await act(async () => regeneration.resolve(regeneratedDraft));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Regenerate' })).toBeEnabled());
  expect(writes()).toHaveLength(2);
  expect(screen.getByRole('combobox', { name: 'Student' })).toHaveValue('ada');
  expect(screen.getByRole('combobox', { name: 'Tone' })).toHaveValue('warm');
}
beforeEach(() => { vi.mocked(api).mockReset(); });

it('replaces an unchanged parent draft after the actual Regenerate POST settles', async () => {
  const regeneration = transport(); const { user, client } = setup();
  const { subject, message } = await beginRegeneration(user);
  await complete(regeneration);
  expect(screen.getByLabelText('Subject')).toBe(subject); expect(subject).toHaveValue(regeneratedDraft.subject);
  expect(screen.getByLabelText('Message')).toBe(message); expect(message).toHaveValue(regeneratedDraft.body);
  expect(screen.getByText('AI draft')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open in email' })).toHaveAttribute('href', `mailto:?subject=${encodeURIComponent(regeneratedDraft.subject)}&body=${encodeURIComponent(regeneratedDraft.body)}`);
  expect(client.getQueryData(['report-summary', 'p1'])).toEqual(summary);
});

it('retains both latest raw teacher fields and their source when Regenerate settles after pending edits', async () => {
  const regeneration = transport(); const { user, client } = setup();
  const { subject, message } = await beginRegeneration(user);
  const editedSubject = '  Teacher revised subject  ';
  const editedMessage = '  Teacher revised message\nKeep this next line  ';
  await user.clear(subject); await user.type(subject, editedSubject);
  await user.clear(message); await user.type(message, editedMessage);
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  expect(writes()).toHaveLength(2);
  await complete(regeneration);
  expect(screen.getByLabelText('Subject')).toBe(subject); expect(subject).toHaveValue(editedSubject);
  expect(screen.getByLabelText('Message')).toBe(message); expect(message).toHaveValue(editedMessage);
  expect(message).toHaveFocus();
  expect(screen.getByText('Template draft')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open in email' })).toHaveAttribute('href', `mailto:?subject=${encodeURIComponent(editedSubject)}&body=${encodeURIComponent(editedMessage)}`);
  expect(client.getQueryData(['report-summary', 'p1'])).toEqual(summary);
});

async function change(user: ReturnType<typeof userEvent.setup>, field: HTMLElement, value: string) {
  await user.clear(field); if (value) await user.type(field, value);
}
async function alternativeReady(user: ReturnType<typeof userEvent.setup>, regeneration: ReturnType<typeof transport>) {
  const fields = await beginRegeneration(user);
  await change(user, fields.subject, '  Teacher subject  ');
  await change(user, fields.message, '  Teacher message\nSecond line  ');
  await complete(regeneration);
  await screen.findByText('A new draft is ready. Your edits were kept.');
  return fields;
}
function email(subject: string, body: string) {
  expect(screen.getByRole('link', { name: 'Open in email' })).toHaveAttribute('href', `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
}

it.each(['subject', 'message', 'away-back'] as const)('counts %s edits independently and keeps both fields with a reviewable alternative', async (kind) => {
  const regeneration = transport(); const { user } = setup(); const { subject, message } = await beginRegeneration(user);
  if (kind === 'message') await change(user, message, '   ');
  else {
    await change(user, subject, '  Changed subject  ');
    if (kind === 'away-back') await change(user, subject, originalDraft.subject);
  }
  await complete(regeneration);
  expect(subject).toHaveValue(kind === 'subject' ? '  Changed subject  ' : originalDraft.subject);
  expect(message).toHaveValue(kind === 'message' ? '   ' : originalDraft.body);
  expect(screen.getByText('Template draft')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Review new draft' })).toBeEnabled();
  expect(screen.queryByRole('button', { name: 'Replace my edited draft' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  const review = screen.getByRole('region', { name: 'New generated draft' });
  expect(within(review).getByText(regeneratedDraft.subject)).toBeInTheDocument();
  expect(within(review).getByText(regeneratedDraft.body)).toBeInTheDocument();
  expect(within(review).queryByRole('textbox')).not.toBeInTheDocument();
  expect(writes()).toHaveLength(2);
});

it('review and further editing keep current copy/email until an explicit replacement installs the whole alternative', async () => {
  const regeneration = transport(); const { user } = setup();
  const { subject, message } = await alternativeReady(user, regeneration);
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  const review = screen.getByRole('region', { name: 'New generated draft' });
  expect(within(review).getByText('New AI draft')).toBeInTheDocument();
  expect(within(review).getByText(regeneratedDraft.subject)).toBeInTheDocument();
  expect(within(review).getByText(regeneratedDraft.body)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Close review' }));
  expect(screen.queryByText(regeneratedDraft.subject)).not.toBeInTheDocument();
  await change(user, subject, '  Edited again after review  ');
  expect(message).toHaveValue('  Teacher message\nSecond line  ');
  email('  Edited again after review  ', '  Teacher message\nSecond line  ');
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  expect(clipboard).toHaveBeenLastCalledWith('Subject:   Edited again after review  \n\n  Teacher message\nSecond line  ');
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  expect(subject).toHaveValue('  Edited again after review  ');
  await user.click(screen.getByRole('button', { name: 'Replace my edited draft' }));
  expect(subject).toHaveValue(regeneratedDraft.subject); expect(message).toHaveValue(regeneratedDraft.body);
  expect(screen.getByText('AI draft')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Copied ✓' })).not.toBeInTheDocument();
  email(regeneratedDraft.subject, regeneratedDraft.body);
  expect(writes()).toHaveLength(2); clipboard.mockRestore();
});

it('discarding an alternative keeps current raw fields and source without another generation', async () => {
  const regeneration = transport(); const { user } = setup();
  const { subject, message } = await alternativeReady(user, regeneration);
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  await user.click(screen.getByRole('button', { name: 'Discard new draft' }));
  expect(subject).toHaveValue('  Teacher subject  '); expect(message).toHaveValue('  Teacher message\nSecond line  ');
  expect(screen.getByText('Template draft')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument();
  email('  Teacher subject  ', '  Teacher message\nSecond line  '); expect(writes()).toHaveLength(2);
});

it('keyboard discard returns focus to Subject and keeps the current raw draft and source', async () => {
  const regeneration = transport(); const { user } = setup(); const { subject, message } = await alternativeReady(user, regeneration);
  expect(message).toHaveFocus();
  await user.tab(); expect(screen.getByRole('button', { name: 'Copy' })).toHaveFocus();
  await user.tab(); expect(screen.getByRole('link', { name: 'Open in email' })).toHaveFocus();
  await user.tab(); expect(screen.getByRole('button', { name: 'Review new draft' })).toHaveFocus();
  await user.tab(); expect(screen.getByRole('button', { name: 'Discard new draft' })).toHaveFocus();
  await user.keyboard('{Enter}');
  expect(subject).toHaveFocus(); expect(subject).toHaveValue('  Teacher subject  '); expect(message).toHaveValue('  Teacher message\nSecond line  ');
  expect(screen.getByText('Template draft')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument(); expect(writes()).toHaveLength(2);
});

it('keyboard review and replace returns focus to Subject with the whole generated alternative', async () => {
  const regeneration = transport(); const { user } = setup(); const { subject, message } = await alternativeReady(user, regeneration);
  expect(message).toHaveFocus();
  await user.tab(); await user.tab(); await user.tab();
  expect(screen.getByRole('button', { name: 'Review new draft' })).toHaveFocus(); await user.keyboard('{Enter}');
  expect(screen.getByText(regeneratedDraft.subject)).toBeInTheDocument(); expect(screen.getByText(regeneratedDraft.body)).toBeInTheDocument();
  await user.tab(); expect(screen.getByRole('button', { name: 'Discard new draft' })).toHaveFocus();
  await user.tab(); expect(screen.getByRole('button', { name: 'Replace my edited draft' })).toHaveFocus(); await user.keyboard('{Enter}');
  expect(subject).toHaveFocus(); expect(subject).toHaveValue(regeneratedDraft.subject); expect(message).toHaveValue(regeneratedDraft.body);
  expect(screen.getByText('AI draft')).toBeInTheDocument(); email(regeneratedDraft.subject, regeneratedDraft.body);
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument(); expect(writes()).toHaveLength(2);
});

it('a deliberate later regeneration replaces the bounded alternative only after its own settlement', async () => {
  const regeneration = transport(); const { user } = setup();
  const { subject, message } = await alternativeReady(user, regeneration);
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  const later = deferred<ParentUpdateOut>(); const ordinary = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) => path.endsWith('/parent-update') ? later.promise as never : ordinary(path, options));
  await user.click(screen.getByRole('button', { name: 'Regenerate' }));
  await waitFor(() => expect(writes()).toHaveLength(3));
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument();
  expect(subject).toHaveValue('  Teacher subject  '); expect(message).toHaveValue('  Teacher message\nSecond line  ');
  await change(user, message, '  Later request teacher edit  ');
  const latest: ParentUpdateOut = { subject: 'Latest generated subject', body: 'Latest generated message', source: 'template' };
  await act(async () => later.resolve(latest));
  await screen.findByRole('button', { name: 'Review new draft' });
  expect(message).toHaveValue('  Later request teacher edit  ');
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  const review = screen.getByRole('region', { name: 'New generated draft' });
  expect(within(review).getByText(latest.subject)).toBeInTheDocument(); expect(within(review).getByText(latest.body)).toBeInTheDocument();
  expect(within(review).getByText('New template draft')).toBeInTheDocument();
  expect(screen.queryByText(regeneratedDraft.subject)).not.toBeInTheDocument(); expect(writes()).toHaveLength(3);
});

it.each([false, true])('failed regeneration retains current fields (changed=%s) and a deliberate retry stays manual', async (changed) => {
  const regeneration = transport(); const { user } = setup(); const { subject, message } = await beginRegeneration(user);
  if (changed) { await change(user, subject, '  Failed request subject  '); await change(user, message, '  Failed request message  '); }
  await act(async () => regeneration.reject(new Error('Generation unavailable')));
  await screen.findByText('Generation unavailable');
  expect(subject).toHaveValue(changed ? '  Failed request subject  ' : originalDraft.subject);
  expect(message).toHaveValue(changed ? '  Failed request message  ' : originalDraft.body);
  expect(screen.getByText('Template draft')).toBeInTheDocument(); expect(writes()).toHaveLength(2);
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument();
  const retry = deferred<ParentUpdateOut>(); const ordinary = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, options) => path.endsWith('/parent-update') ? retry.promise as never : ordinary(path, options));
  await user.click(screen.getByRole('button', { name: 'Regenerate' }));
  await waitFor(() => expect(writes()).toHaveLength(3));
  expect(writes()[2]).toEqual(['/reports/students/ada/parent-update', { method: 'POST', body: { tone: 'warm', expected_section_id: 'p1' } }]);
  await act(async () => retry.resolve(regeneratedDraft));
  await waitFor(() => expect(subject).toHaveValue(regeneratedDraft.subject));
  expect(message).toHaveValue(regeneratedDraft.body); expect(screen.queryByText('Generation unavailable')).not.toBeInTheDocument();
});

it.each(['success', 'error'] as const)('alternative arrival preserves current clipboard %s feedback', async (outcome) => {
  const regeneration = transport(); const { user } = setup(); const { subject, message } = await beginRegeneration(user);
  await change(user, subject, '  Copy this teacher subject  ');
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText');
  if (outcome === 'error') clipboard.mockRejectedValue(new Error('Clipboard unavailable')); else clipboard.mockResolvedValue(undefined);
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  if (outcome === 'success') await screen.findByRole('button', { name: 'Copied ✓' });
  else await screen.findByText(/Copy could not be completed/);
  await complete(regeneration);
  expect(subject).toHaveValue('  Copy this teacher subject  '); expect(message).toHaveValue(originalDraft.body);
  if (outcome === 'success') expect(screen.getByRole('button', { name: 'Copied ✓' })).toBeInTheDocument();
  else expect(screen.getByText(/Copy could not be completed/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Review new draft' })).toBeInTheDocument(); clipboard.mockRestore();
});

it('a clipboard operation without text edits does not turn unchanged regeneration into a conflict', async () => {
  const regeneration = transport(); const { user } = setup(); const { subject } = await beginRegeneration(user);
  const clipboard = deferred<void>(); const write = vi.spyOn(navigator.clipboard, 'writeText').mockReturnValue(clipboard.promise);
  await user.click(screen.getByRole('button', { name: 'Copy' })); await complete(regeneration);
  expect(subject).toHaveValue(regeneratedDraft.subject); expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument();
  await act(async () => clipboard.resolve());
  expect(screen.queryByRole('button', { name: 'Copied ✓' })).not.toBeInTheDocument(); write.mockRestore();
});

it.each(['edit', 'replace'] as const)('late clipboard completion cannot claim copying the current draft after %s', async (action) => {
  const regeneration = transport(); const { user } = setup(); const { subject } = await alternativeReady(user, regeneration);
  const clipboard = deferred<void>(); const write = vi.spyOn(navigator.clipboard, 'writeText').mockReturnValue(clipboard.promise);
  await user.click(screen.getByRole('button', { name: 'Copy' }));
  if (action === 'edit') await change(user, subject, '  Later current subject  ');
  else { await user.click(screen.getByRole('button', { name: 'Review new draft' })); await user.click(screen.getByRole('button', { name: 'Replace my edited draft' })); }
  await act(async () => clipboard.resolve()); expect(screen.queryByRole('button', { name: 'Copied ✓' })).not.toBeInTheDocument();
  expect(subject).toHaveValue(action === 'edit' ? '  Later current subject  ' : regeneratedDraft.subject); write.mockRestore();
});

async function switchBoundary(user: ReturnType<typeof userEvent.setup>, boundary: string) {
  if (boundary === 'student') {
    await user.selectOptions(screen.getByRole('combobox', { name: 'Student' }), 'ben');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Student' }), 'ada');
  } else if (boundary === 'tone') {
    await user.selectOptions(screen.getByRole('combobox', { name: 'Tone' }), 'neutral');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Tone' }), 'warm');
  } else if (boundary === 'section') {
    await user.selectOptions(screen.getByRole('combobox', { name: 'Section' }), 'p2');
    await screen.findByText('Period 2 · class snapshot and parent updates');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Section' }), 'p1');
    await screen.findByRole('option', { name: 'Ada' });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Student' }), 'ada');
  } else await user.click(screen.getByRole('button', { name: 'Clear selection' }));
}

it.each(['student', 'tone', 'section'] as const)('late pending regeneration is discarded after actual %s ABA', async (boundary) => {
  const regeneration = transport(); const { user } = setup(); const { subject } = await beginRegeneration(user);
  await change(user, subject, '  Old lifecycle edit  '); await switchBoundary(user, boundary);
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
  await act(async () => regeneration.resolve(regeneratedDraft));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Generate draft' })).toBeEnabled());
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument(); expect(writes()).toHaveLength(2);
});

it.each(['student', 'tone', 'section', 'selection', 'roster'] as const)('a retained alternative is cleared on actual %s reset', async (boundary) => {
  const regeneration = transport(); const { user, client } = setup(); await alternativeReady(user, regeneration);
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  if (boundary === 'roster') await act(async () => { await client.invalidateQueries({ queryKey: ['students'] }); });
  else await switchBoundary(user, boundary);
  await waitFor(() => expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument());
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument(); expect(writes()).toHaveLength(2);
});

it.each(['success', 'error'] as const)('summary day refresh %s keeps edited fields and the reviewable alternative without another POST', async (outcome) => {
  const regeneration = transport(); const { user, client } = setup(); const { subject, message } = await alternativeReady(user, regeneration);
  const read = deferred<ClassSummary>(); const ordinary = vi.mocked(api).getMockImplementation()!;
  let signal: AbortSignal | undefined;
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/reports/sections/p1/summary') { signal = options?.signal; return read.promise as never; }
    return ordinary(path, options);
  });
  await act(async () => { client.setQueryData(['school-calendar'], { timezone: 'America/Los_Angeles', today: '2026-10-03' }); });
  await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/reports/sections/p1/summary')).toHaveLength(2));
  expect(signal).toBeInstanceOf(AbortSignal);
  await act(async () => { if (outcome === 'error') read.reject(new Error('Summary read unavailable')); else read.resolve({ ...summary, as_of: '2026-10-03' }); });
  if (outcome === 'error') await screen.findByText('Summary read unavailable'); else await screen.findByText('Summary calculated through 2026-10-03');
  expect(subject).toHaveValue('  Teacher subject  '); expect(message).toHaveValue('  Teacher message\nSecond line  ');
  await user.click(screen.getByRole('button', { name: 'Review new draft' }));
  expect(screen.getByText(regeneratedDraft.subject)).toBeInTheDocument(); expect(screen.getByText(regeneratedDraft.body)).toBeInTheDocument();
  expect(client.getQueryData(['report-summary', 'p1'])).toEqual(outcome === 'error' ? summary : { ...summary, as_of: '2026-10-03' });
  expect(writes()).toHaveLength(2);
});

let Root: typeof import('../main')['Root'];
beforeAll(async () => {
  const element = document.createElement('div'); element.id = 'root'; document.body.append(element);
  try { ({ Root } = await import('../main')); } finally { element.remove(); }
});

it.each(['expiry/pending', 'logout/pending', 'expiry/ready', 'logout/ready'])('actual Root %s discards private alternative ownership and isolates the next same-student draft', async (scenario) => {
  const regeneration = transport(); const ordinary = vi.mocked(api).getMockImplementation()!;
  const actualApi = (await vi.importActual<typeof import('../api')>('../api')).api;
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }));
  let newSession = false;
  const newDraft: ParentUpdateOut = { subject: 'Next session subject', body: 'Next session body', source: 'template' };
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === '/session-probe') return actualApi(path, options);
    if (path === '/auth/config') return { auth_mode: 'passcode' } as never;
    if (path === '/auth/me') return { authenticated: true, auth_required: true } as never;
    if (path === '/auth/login' || path === '/auth/logout') return {} as never;
    if (newSession && path.endsWith('/parent-update')) return newDraft as never;
    return ordinary(path, options);
  });
  const clients: QueryClient[] = []; let logout!: () => void;
  function Probe() {
    const client = useQueryClient(); if (!clients.includes(client)) clients.push(client); logout = useAuth().logout;
    return <MemoryRouter><ScopeProvider><Reports /></ScopeProvider></MemoryRouter>;
  }
  localStorage.setItem('st-theme', 'dark'); const view = render(<Root><Probe /></Root>); const user = userEvent.setup();
  const fields = await beginRegeneration(user); await change(user, fields.subject, '  Old session edit  ');
  if (scenario.endsWith('ready')) { await complete(regeneration); await screen.findByRole('button', { name: 'Review new draft' }); }
  const old = clients.at(-1)!;
  await act(async () => { if (scenario.startsWith('logout')) logout(); else await api('/session-probe').catch(() => {}); });
  await screen.findByRole('heading', { name: 'Sign in' });
  expect(screen.queryByLabelText('Subject')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument(); expect(old.getQueryCache().getAll()).toHaveLength(0);
  newSession = true; await user.type(screen.getByLabelText('Passcode'), 'new-passcode'); await user.click(screen.getByRole('button', { name: 'Sign in' }));
  await screen.findByRole('option', { name: 'Ada' }); await user.selectOptions(screen.getByRole('combobox', { name: 'Student' }), 'ada');
  await user.click(screen.getByRole('button', { name: 'Generate draft' }));
  const subject = await screen.findByLabelText('Subject'); const message = screen.getByLabelText('Message');
  expect(subject).not.toBe(fields.subject); await change(user, subject, '  Next session teacher subject  '); await change(user, message, '  Next session teacher message  ');
  const current = clients.at(-1)!; expect(current).not.toBe(old); const invalidate = vi.spyOn(current, 'invalidateQueries');
  const before = vi.mocked(api).mock.calls.length;
  if (scenario.endsWith('pending')) await act(async () => regeneration.resolve(regeneratedDraft));
  expect(vi.mocked(api).mock.calls).toHaveLength(before); expect(invalidate).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Subject')).toBe(subject); expect(subject).toHaveValue('  Next session teacher subject  '); expect(message).toHaveValue('  Next session teacher message  ');
  expect(screen.queryByRole('region', { name: 'New generated draft' })).not.toBeInTheDocument();
  expect(current.getQueryData(['report-summary', 'p1'])).toEqual(summary); expect(old.getQueryCache().getAll()).toHaveLength(0);
  expect(localStorage.getItem('st-theme')).toBe('dark');
  if (scenario.startsWith('expiry')) expect(fetchMock).toHaveBeenCalledWith('/api/session-probe', expect.objectContaining({ method: 'GET' }));
  else expect(api).toHaveBeenCalledWith('/auth/logout', { method: 'POST' });
  view.unmount(); fetchMock.mockRestore();
});
