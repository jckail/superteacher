import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { RiskChip } from '../components/ui';
import { ToastProvider } from '../components/Toast';
import { ScopeProvider } from '../scope';
import Overview from '../pages/Overview';
import Reports from '../pages/Reports';
import Roster from '../pages/Roster';
import type { ClassSummary, Course, Overview as OverviewData, StudentSummary } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));

const courses: Course[] = [
  { id: 'math', name: 'Math', sections: [{ id: 'p1', name: 'Period 1', course_id: 'math' }, { id: 'p2', name: 'Period 2', course_id: 'math' }] },
  { id: 'science', name: 'Science', sections: [{ id: 'p3', name: 'Period 3', course_id: 'science' }] },
];

const concern: StudentSummary = {
  id: 'concern', name: 'Known concern', grade_level: 7, course_id: 'math', course: 'Math', section_id: 'p1', section: 'Period 1',
  average: 0, letter: 'F', gpa: 0, attendance_rate: null, homework_rate: null, trend: null, missing: 0,
  risk: 'at_risk', risk_reasons: ['Average 0% is failing'],
};
const base: OverviewData = {
  students: 3, average: null, attendance_rate: null, homework_rate: null,
  unknown: 3, on_track: 0, watch: 0, at_risk: 0, distribution: { A: 0, B: 0, C: 0, D: 0, F: 0 }, attention: [],
};
const overviewData = (kind: 'unknown' | 'partlyUnknown' | 'mixed' | 'healthy'): OverviewData => {
  if (kind === 'partlyUnknown') return { ...base, unknown: 1, on_track: 2, average: 90 };
  if (kind === 'mixed') return { ...base, unknown: 1, watch: 1, at_risk: 1, average: 35, attention: [concern, { ...concern, id: 'watch', name: 'Known watch', risk: 'watch' }] };
  if (kind === 'healthy') return { ...base, unknown: 0, on_track: 3, average: 90 };
  return base;
};
const classData = (o: OverviewData): ClassSummary => ({
  as_of: '2026-10-02', section_id: 'p1', section: 'Period 1', course: 'Math', students: o.students,
  unknown: o.unknown, on_track: o.on_track, watch: o.watch, at_risk: o.at_risk, average: o.average,
  distribution: o.distribution, assessments: [], attendance: [], attendance_rate: o.attendance_rate,
  attention: o.attention.map((s) => ({ id: s.id, name: s.name, risk: s.risk, average: s.average, reasons: s.risk_reasons })),
});
function mount(page: 'overview' | 'reports', data: OverviewData) {
  vi.mocked(api).mockImplementation(async (path) => (path === '/courses' ? courses : path.startsWith('/overview') ? data : path.endsWith('/summary') ? classData(data) : []) as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><ScopeProvider>{page === 'overview' ? <Overview /> : <Reports />}</ScopeProvider></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { vi.mocked(api).mockReset(); });

describe.each(['overview', 'reports'] as const)('%s evidence copy', (page) => {
  it('asks for records when the entire roster lacks evidence', async () => {
    mount(page, overviewData('unknown'));
    expect(await screen.findByText('Record work or attendance before assessing progress.')).toBeInTheDocument();
    expect(screen.getByText('Not enough data')).toBeInTheDocument();
    expect(screen.getByText(/3 students lack enough data/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review records needing data' })).toHaveAttribute('href', '/roster?status=unknown');
    expect(screen.queryByText('Everyone is on track.')).not.toBeInTheDocument();
    expect(screen.queryByText(/Nobody is flagged/)).not.toBeInTheDocument();
    expect(screen.queryByText(/🎉/)).not.toBeInTheDocument();
  });
  it('qualifies no-flags copy when some students lack evidence', async () => {
    mount(page, overviewData('partlyUnknown'));
    expect(await screen.findByText('No attention flags among students with evidence.')).toBeInTheDocument();
    expect(screen.getByText(/1 student lacks enough data/)).toBeInTheDocument();
    expect(screen.queryByText('Everyone is on track.')).not.toBeInTheDocument();
    expect(screen.queryByText(/🎉/)).not.toBeInTheDocument();
  });
  it('keeps known concerns visible and separates missing evidence', async () => {
    mount(page, overviewData('mixed'));
    expect(await screen.findByText('Known concern')).toBeInTheDocument();
    expect(screen.getByText('Known watch')).toBeInTheDocument();
    expect(screen.getByText(/1 student lacks enough data/)).toBeInTheDocument();
    expect(screen.queryByText('Everyone is on track.')).not.toBeInTheDocument();
  });
  it('keeps healthy-roster copy when all students have evidence', async () => {
    mount(page, overviewData('healthy'));
    expect(await screen.findByText(page === 'overview' ? 'Nobody is flagged. 🎉' : 'Nobody is flagged right now.')).toBeInTheDocument();
    if (page === 'overview') expect(screen.getByText('Everyone is on track.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Review records needing data' })).not.toBeInTheDocument();
  });
});

it('labels an unknown risk chip with its neutral evidence class', () => {
  render(<RiskChip risk="unknown" />);
  expect(screen.getByText('Not enough data')).toHaveClass('chip', 'unknown');
  expect(screen.getByText('Not enough data')).not.toHaveClass('on_track', 'watch', 'at_risk');
});


describe.each(['all', 'course'] as const)('report review navigation from %s scope', (scope) => {
  it('keeps the default report section instead of broadening to other sections', async () => {
    if (scope === 'course') localStorage.setItem('st-scope', JSON.stringify({ courseId: 'math', sectionId: null }));
    const unknown = (id: string, name: string, sectionId: string): StudentSummary => ({
      ...concern, id, name, section_id: sectionId, section: sectionId === 'p1' ? 'Period 1' : 'Period 2',
      average: null, letter: null, gpa: null, risk: 'unknown', risk_reasons: [],
    });
    const students = [unknown('default', 'Default section learner', 'p1'), unknown('other', 'Other section learner', 'p2')];
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === '/courses') return courses as never;
      if (path.endsWith('/summary')) return classData({ ...base, students: 1, unknown: 1 }) as never;
      if (path.startsWith('/students?')) {
        const sectionId = new URLSearchParams(path.split('?')[1]).get('section_id');
        return students.filter((student) => !sectionId || student.section_id === sectionId) as never;
      }
      if (path.startsWith('/students/page?')) {
        const params = new URLSearchParams(path.split('?')[1]);
        const scoped = students.filter((student) => (!params.get('section_id') || student.section_id === params.get('section_id')) && (!params.get('course_id') || student.course_id === params.get('course_id')));
        const matches = scoped.filter((student) => !params.get('risk') || student.risk === params.get('risk'));
        return { items: matches, next_cursor: null, as_of: '2026-10-02', total_matches: matches.length, total_scoped: scoped.length } as never;
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}><MemoryRouter initialEntries={['/reports']}><ScopeProvider><ToastProvider>
        <Routes><Route path="/reports" element={<Reports />} /><Route path="/roster" element={<Roster />} /></Routes>
      </ToastProvider></ScopeProvider></MemoryRouter></QueryClientProvider>,
    );
    await screen.findByText(/1 student lacks enough data/);
    expect(api).toHaveBeenCalledWith('/reports/sections/p1/summary', expect.anything());
    // Global section is still All while the report uses the first section by default.
    expect(JSON.parse(localStorage.getItem('st-scope') ?? '{}').sectionId).toBeNull();
    await userEvent.setup().click(screen.getByRole('link', { name: 'Review records needing data' }));
    expect(await screen.findByRole('link', { name: 'Default section learner' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Other section learner' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Not enough data' })).toHaveAttribute('aria-pressed', 'true');
    const selection = JSON.parse(localStorage.getItem('st-scope') ?? '{}');
    expect(selection).toEqual({ courseId: scope === 'course' ? 'math' : null, sectionId: 'p1' });
    const rosterRequests = vi.mocked(api).mock.calls.filter(([path]) => path.startsWith('/students?') || path.startsWith('/students/page?'));
    expect(rosterRequests.length).toBeGreaterThan(1);
    for (const [path] of rosterRequests) expect(new URLSearchParams(path.split('?')[1]).get('section_id')).toBe('p1');
    expect(rosterRequests.some(([path]) => path.startsWith('/students?'))).toBe(true); // Reports picker keeps its complete array contract.
    const pagedRequests = rosterRequests.filter(([path]) => path.startsWith('/students/page?'));
    expect(pagedRequests.length).toBeGreaterThan(0);
    for (const [path] of pagedRequests) {
      const params = new URLSearchParams(path.split('?')[1]);
      expect(params.get('risk')).toBe('unknown');
      expect(params.get('limit')).toBe('50');
      expect(params.get('course_id')).toBe(scope === 'course' ? 'math' : null);
    }
  });
});
