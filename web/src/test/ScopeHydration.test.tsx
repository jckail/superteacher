import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, UNAUTHORIZED_EVENT } from '../api';
import { AuthGate } from '../auth';
import { ScopeProvider } from '../scope';
import { ToastProvider } from '../components/Toast';
import Roster from '../pages/Roster';
import Overview from '../pages/Overview';
import Reports from '../pages/Reports';
import Gradebook from '../pages/Gradebook';
import Attendance from '../pages/Attendance';
import type { CourseOut, StudentPage, StudentSummary } from '../types';
vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
const courses: CourseOut[] = [{ id: 'saved-course', name: 'Saved course', sections: [{ id: 'saved-section', name: 'Saved section', course_id: 'saved-course' }] }, { id: 'other-course', name: 'Other course', sections: [{ id: 'other-section', name: 'Other section', course_id: 'other-course' }] }];
const student = (name: string): StudentSummary => ({ id: name, name, grade_level: 9, section_id: 'saved-section', section: 'Saved section', course_id: 'saved-course', course: 'Saved course', average: null, letter: null, gpa: null, trend: null, attendance_rate: null, homework_rate: null, missing: 0, risk: 'unknown', risk_reasons: [] });
const page = (name: string): StudentPage => ({ items: [student(name)], next_cursor: null, as_of: '2026-10-02', total_matches: 1, total_scoped: 1 });
function deferred<T>() { let resolve!: (v: T) => void; let reject!: (e: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
const pages = { roster: Roster, overview: Overview, reports: Reports, gradebook: Gradebook, attendance: Attendance };
function setup(kind: keyof typeof pages = 'roster', saved: { courseId: string | null; sectionId: string | null } | null = { courseId: 'saved-course', sectionId: 'saved-section' }, auth = false) {
  if (saved) localStorage.setItem('st-scope', JSON.stringify(saved));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  const Component = pages[kind];
  const privateTree = <><p>Shell remains accessible</p><ScopeProvider><ToastProvider><MemoryRouter><Component /></MemoryRouter></ToastProvider></ScopeProvider></>;
  const view = render(<QueryClientProvider client={client}>{auth ? <AuthGate onLogout={() => client.clear()}>{privateTree}</AuthGate> : privateTree}</QueryClientProvider>);
  return { ...view, client, user: userEvent.setup() };
}
function studentRequests() { return vi.mocked(api).mock.calls.filter(([path]) => path.startsWith('/students/page')); }
beforeEach(() => { vi.mocked(api).mockReset(); });

describe('saved scope hydration', () => {
  it('makes no broader roster request while saved metadata is pending, then loads only that scope', async () => {
    const metadata = deferred<CourseOut[]>();
    vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? metadata.promise : page('SCOPED ROW'));
    setup();
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/courses', expect.anything()));
    expect(studentRequests()).toHaveLength(0);
    expect(screen.getByText('Shell remains accessible')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Course' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '+ Student' })).toBeDisabled();
    await act(async () => metadata.resolve(courses));
    await screen.findByText('SCOPED ROW');
    const params = new URLSearchParams(studentRequests()[0][0].split('?')[1]);
    expect(params.get('course_id')).toBe('saved-course');
    expect(params.get('section_id')).toBe('saved-section');
    expect(studentRequests()).toHaveLength(1);
  });

  it('Overview waits for saved metadata before loading its cutoff and school calendar', async () => {
    const metadata = deferred<CourseOut[]>();
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === '/courses') return metadata.promise;
      if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-10-02' };
      if (path === '/overview?course_id=saved-course&section_id=saved-section') return { as_of: '2026-10-02', students: 0, average: null, attendance_rate: null, homework_rate: null, unknown: 0, on_track: 0, watch: 0, at_risk: 0, distribution: { A: 0, B: 0, C: 0, D: 0, F: 0 }, attention: [] };
      throw new Error(`Unexpected request ${path}`);
    });
    setup('overview');
    await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    expect(screen.queryByText(/Progress calculated through/)).not.toBeInTheDocument();
    await act(async () => metadata.resolve(courses));
    await screen.findByText('Progress calculated through 2026-10-02');
    expect(screen.getByText('No students yet')).toBeInTheDocument();
    expect(vi.mocked(api).mock.calls.map(([path]) => path).sort()).toEqual(['/calendar', '/courses', '/overview?course_id=saved-course&section_id=saved-section']);
    expect(screen.getByText('Shell remains accessible')).toBeInTheDocument();
  });

  it.each(['overview', 'reports', 'gradebook', 'attendance'] as const)('%s waits for metadata and shows its failure rather than false empty data', async (kind) => {
    const metadata = deferred<CourseOut[]>();
    vi.mocked(api).mockImplementation(async (path) => { if (path === '/courses') return metadata.promise; throw new Error(`Unexpected scoped read ${path}`); });
    setup(kind);
    await vi.waitFor(() => expect(api).toHaveBeenCalledOnce());
    await act(async () => metadata.reject(new Error('COURSES FAILED')));
    await screen.findByText('COURSES FAILED');
    expect(screen.getByRole('button', { name: 'Retry courses' })).toBeInTheDocument();
    expect(screen.queryByText(/Create a course and section/)).not.toBeInTheDocument();
    expect(screen.queryByText('No classes yet')).not.toBeInTheDocument();
    expect(api).toHaveBeenCalledOnce();
    expect(screen.getByText('Shell remains accessible')).toBeInTheDocument();
  });

  it('metadata error retains saved selection and retry resolves it without broader rows', async () => {
    let metadataCalls = 0;
    vi.mocked(api).mockImplementation(async (path) => { if (path === '/courses') { metadataCalls++; if (metadataCalls === 1) throw new Error('COURSES FAILED'); return courses; } return page('RETRIED SCOPE'); });
    const { user } = setup();
    await screen.findByText('COURSES FAILED');
    expect(studentRequests()).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem('st-scope') ?? '{}')).toEqual({ courseId: 'saved-course', sectionId: 'saved-section' });
    await user.click(screen.getByRole('button', { name: 'Retry courses' })); await screen.findByText('RETRIED SCOPE');
    expect(studentRequests()).toHaveLength(1);
    expect(new URLSearchParams(studentRequests()[0][0].split('?')[1]).get('section_id')).toBe('saved-section');
  });

  it.each([{ courseId: 'saved-course', sectionId: null }, { courseId: null, sectionId: 'saved-section' }])('restores course-only or section-only scope %j', async (saved) => {
    vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? courses : page('RESTORED'));
    setup('roster', saved); await screen.findByText('RESTORED');
    const params = new URLSearchParams(studentRequests()[0][0].split('?')[1]);
    expect(params.get('course_id')).toBe(saved.courseId);
    expect(params.get('section_id')).toBe(saved.sectionId);
  });

  it('keeps deliberate All with no saved selection and successful empty metadata as a valid empty roster', async () => {
    vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? [] : { ...page('unused'), items: [], total_matches: 0, total_scoped: 0 });
    setup('roster', null); await screen.findByText('No students yet');
    const params = new URLSearchParams(studentRequests()[0][0].split('?')[1]);
    expect(params.get('course_id')).toBeNull(); expect(params.get('section_id')).toBeNull();
    expect(screen.getByRole('combobox', { name: 'Course' })).toHaveValue('');
    expect(screen.queryByText(/saved scope is unavailable/)).not.toBeInTheDocument();
  });

  it.each([{ courseId: 'missing-course', sectionId: null }, { courseId: 'saved-course', sectionId: 'missing-section' }, { courseId: 'saved-course', sectionId: 'other-section' }])('missing or incompatible saved IDs %j require explicit scope choice', async (saved) => {
    vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? courses : page('CHOSEN SCOPE'));
    const { user } = setup('roster', saved);
    await screen.findByText(/Your saved scope is unavailable\./);
    expect(studentRequests()).toHaveLength(0);
    expect(screen.queryByText('CHOSEN SCOPE')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Student' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Use all courses' }));
    await screen.findByText('CHOSEN SCOPE');
    expect(studentRequests()).toHaveLength(1);
    expect(new URLSearchParams(studentRequests()[0][0].split('?')[1]).get('course_id')).toBeNull();
    expect(JSON.parse(localStorage.getItem('st-scope') ?? '{}')).toEqual({ courseId: null, sectionId: null });
  });

  it('missing section recovery can choose another section without broadening its course', async () => {
    vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? courses : page('CURRENT SECTION'));
    const { user } = setup('roster', { courseId: 'saved-course', sectionId: 'missing-section' });
    await screen.findByText(/Your saved scope is unavailable\./);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Section' }), 'saved-section');
    await screen.findByText('CURRENT SECTION');
    const params = new URLSearchParams(studentRequests()[0][0].split('?')[1]);
    expect(params.get('course_id')).toBe('saved-course'); expect(params.get('section_id')).toBe('saved-section');
  });

  it('background metadata errors preserve verified scope/rows and expose a retry warning', async () => {
    let metadataCalls = 0;
    vi.mocked(api).mockImplementation(async (path) => { if (path === '/courses') { metadataCalls++; if (metadataCalls === 2) throw new Error('REFRESH FAILED'); return courses; } return page('VERIFIED ROW'); });
    const { client, user } = setup(); await screen.findByText('VERIFIED ROW');
    await act(async () => { await client.invalidateQueries({ queryKey: ['courses'] }); });
    await screen.findByText('REFRESH FAILED');
    expect(screen.getByText('VERIFIED ROW')).toBeInTheDocument();
    expect(studentRequests()).toHaveLength(1);
    expect(screen.getByRole('combobox', { name: 'Course' })).toHaveValue('saved-course');
    await user.click(screen.getByRole('button', { name: 'Retry courses' }));
    await vi.waitFor(() => expect(screen.queryByText('REFRESH FAILED')).not.toBeInTheDocument());
    expect(studentRequests()).toHaveLength(1);
  });

  it('successful metadata removal hides old rows and aborts a pending scoped page until user chooses scope', async () => {
    const pending = deferred<StudentPage>(); let metadataCalls = 0; let rosterCalls = 0;
    vi.mocked(api).mockImplementation(async (path) => { if (path === '/courses') return ++metadataCalls === 1 ? courses : []; rosterCalls++; return rosterCalls === 1 ? { ...page('OLD VERIFIED'), next_cursor: 'old-cursor', total_matches: 51 } : pending.promise; });
    const { client, user } = setup(); await screen.findByText('OLD VERIFIED');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    const signal = studentRequests()[1][1]?.signal;
    await act(async () => { await client.invalidateQueries({ queryKey: ['courses'] }); });
    await screen.findByText(/Your saved scope is unavailable\./);
    expect(signal?.aborted).toBe(true);
    await act(async () => pending.resolve(page('LATE OLD')));
    expect(screen.queryByText('OLD VERIFIED')).not.toBeInTheDocument();
    expect(screen.queryByText('LATE OLD')).not.toBeInTheDocument();
    expect(studentRequests()).toHaveLength(2);
  });

  it('current metadata401 tears down private UI before any scoped read', async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path.startsWith('/auth/')) return { auth_mode: 'passcode', authenticated: true, auth_required: true };
      if (path === '/courses') { window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)); throw new ApiError(401, 'Unauthorized'); }
      return page('PRIVATE ROW');
    });
    setup('roster', undefined, true);
    await screen.findByRole('heading', { name: 'Sign in' });
    expect(screen.queryByText('Shell remains accessible')).not.toBeInTheDocument();
    expect(screen.queryByText('PRIVATE ROW')).not.toBeInTheDocument();
    expect(studentRequests()).toHaveLength(0);
  });
  it.each(['reports', 'gradebook', 'attendance'] as const)('%s keeps a valid empty course instead of taking another course section', async (kind) => {
    const metadata: CourseOut[] = [{ id: 'empty-course', name: 'Empty course', sections: [] }, ...courses];
    vi.mocked(api).mockImplementation(async (path) => { if (path === '/courses') return metadata; throw new Error(`Unexpected other-course read ${path}`); });
    setup(kind, { courseId: 'empty-course', sectionId: null });
    await screen.findByText(kind === 'reports' ? 'Create a course and section on the roster first.' : 'No classes yet');
    expect(api).toHaveBeenCalledOnce();
  });

  it('auth expiry while metadata is pending aborts it and rejects its late result', async () => {
    const metadata = deferred<CourseOut[]>();
    vi.mocked(api).mockImplementation(async (path) => path.startsWith('/auth/') ? { auth_mode: 'passcode', authenticated: true, auth_required: true } : path === '/courses' ? metadata.promise : page('PRIVATE ROW'));
    setup('roster', undefined, true);
    await screen.findByText('Shell remains accessible');
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith('/courses', expect.anything()));
    const signal = vi.mocked(api).mock.calls.find(([path]) => path === '/courses')?.[1]?.signal;
    act(() => window.dispatchEvent(new Event(UNAUTHORIZED_EVENT)));
    await screen.findByRole('heading', { name: 'Sign in' });
    expect(signal?.aborted).toBe(true);
    await act(async () => metadata.resolve(courses));
    expect(screen.queryByText('Shell remains accessible')).not.toBeInTheDocument();
    expect(screen.queryByText('PRIVATE ROW')).not.toBeInTheDocument();
    expect(studentRequests()).toHaveLength(0);
  });

  it('missing course recovery can explicitly select an available course', async () => {
    vi.mocked(api).mockImplementation(async (path) => path === '/courses' ? courses : page('CURRENT COURSE'));
    const { user } = setup('roster', { courseId: 'missing-course', sectionId: 'missing-section' });
    await screen.findByText(/Your saved scope is unavailable\./);
    expect(screen.getByRole('combobox', { name: 'Course' })).toHaveValue('missing-course');
    expect(screen.getByRole('combobox', { name: 'Section' })).toBeDisabled();
    expect(screen.getByText(/Your saved scope is unavailable\./)).toHaveTextContent('Choose a current course to continue.');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Course' }), 'other-course');
    await screen.findByText('CURRENT COURSE');
    const params = new URLSearchParams(studentRequests()[0][0].split('?')[1]);
    expect(params.get('course_id')).toBe('other-course'); expect(params.get('section_id')).toBeNull();
  });

  it.each(['reports', 'gradebook', 'attendance'] as const)('%s exposes cached metadata refresh failures even with no classes', async (kind) => {
    let count = 0;
    vi.mocked(api).mockImplementation(async () => { if (++count === 1) return []; throw new Error('EMPTY REFRESH FAILED'); });
    const { client } = setup(kind, null);
    await screen.findByText(kind === 'reports' ? 'Create a course and section on the roster first.' : 'No classes yet');
    await act(async () => { await client.invalidateQueries({ queryKey: ['courses'] }); });
    await screen.findByText('EMPTY REFRESH FAILED');
    expect(screen.getByRole('button', { name: 'Retry courses' })).toBeInTheDocument();
    expect(screen.getByText(kind === 'reports' ? 'Create a course and section on the roster first.' : 'No classes yet')).toBeInTheDocument();
  });

  it('an open class draft blocks new submission after saved scope becomes unavailable without discarding draft', async () => {
    let metadataCalls = 0;
    vi.mocked(api).mockImplementation(async (path, options) => { if (path === '/courses' && options?.method !== 'POST') return ++metadataCalls === 1 ? courses : []; if (path === '/courses') throw new Error('Unexpected class write'); return page('VERIFIED'); });
    const { client, user } = setup(); await screen.findByText('VERIFIED');
    await user.click(screen.getByRole('button', { name: '+ Course' }));
    await user.type(screen.getByLabelText('Course name'), 'Unsubmitted draft');
    await act(async () => { await client.invalidateQueries({ queryKey: ['courses'] }); });
    await screen.findByText('Restore your scope before saving this draft.');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Course name')).toHaveValue('Unsubmitted draft');
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled();
    fireEvent.submit(screen.getByLabelText('Course name').closest('form')!);
    expect(vi.mocked(api).mock.calls.some(([path, options]) => path === '/courses' && options?.method === 'POST')).toBe(false);
  });

  it('an already pending class write stays frozen across scope loss and settles normally', async () => {
    const write = deferred<unknown>(); let metadataCalls = 0;
    vi.mocked(api).mockImplementation(async (path, options) => { if (path === '/courses' && options?.method === 'POST') return write.promise; if (path === '/courses') return ++metadataCalls === 1 ? courses : []; return page('VERIFIED'); });
    const { client, user } = setup(); await screen.findByText('VERIFIED');
    await user.click(screen.getByRole('button', { name: '+ Course' })); await user.type(screen.getByLabelText('Course name'), 'Pending class');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await act(async () => { await client.invalidateQueries({ queryKey: ['courses'] }); });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByLabelText('Course name')).toBeDisabled();
    await act(async () => write.resolve({}));
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText(/Your saved scope is unavailable\./)).toBeInTheDocument();
  });

  it.each(['reports', 'gradebook', 'attendance'] as const)('%s switches directly from an empty selected course to an existing course', async (kind) => {
    const metadata: CourseOut[] = [{ id: 'empty-course', name: 'Empty course', sections: [] }, ...courses];
    const section = courses[0].sections[0];
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === '/courses') return metadata;
      if (path === '/calendar') return { timezone: 'UTC', today: '2026-10-02' };
      if (path.startsWith('/students/page?')) return { items: [], next_cursor: null, as_of: '2026-10-02', total_matches: 0, total_scoped: 0 };
      if (path.endsWith('/summary')) return { as_of: '2026-10-02', section_id: section.id, section: section.name, course: 'Saved course', students: 0, unknown: 0, on_track: 0, watch: 0, at_risk: 0, average: null, distribution: {}, assessments: [], attention: [], attendance: [], attendance_rate: null };
      if (path.endsWith('/gradebook')) return { as_of: '2026-10-02', section, assessments: [], rows: [] };
      if (path.includes('/attendance?')) return { section, day: '2026-10-02', rows: [] };
      throw new Error(`Unexpected request ${path}`);
    });
    const { user } = setup(kind, { courseId: 'empty-course', sectionId: null });
    await screen.findByText(kind === 'reports' ? 'Create a course and section on the roster first.' : 'No classes yet');
    expect(api).toHaveBeenCalledOnce();
    const picker = screen.getByRole('combobox', { name: 'Course' });
    expect(picker).toHaveValue('empty-course');
    await user.selectOptions(picker, 'saved-course');
    const expected = kind === 'reports' ? '/reports/sections/saved-section/summary' : kind === 'gradebook' ? '/sections/saved-section/gradebook' : '/sections/saved-section/attendance?day=2026-10-02';
    await vi.waitFor(() => expect(api).toHaveBeenCalledWith(expected, expect.anything()));
    expect(screen.getByRole('combobox', { name: 'Course' })).toHaveValue('saved-course');
    expect(vi.mocked(api).mock.calls.some(([path]) => path.includes('other-section'))).toBe(false);
    expect(JSON.parse(localStorage.getItem('st-scope') ?? '{}')).toEqual({ courseId: 'saved-course', sectionId: null });
  });

});
