import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import AssessmentAnalysis from '../components/AssessmentAnalysis';
import Reports from '../pages/Reports';
import type { AssessmentStat, ClassSummary } from '../types';

vi.mock('../api', async (load) => ({ ...await load<typeof import('../api')>(), api: vi.fn() }));
vi.mock('../scope', () => ({ useActiveSection: () => ({ id: 'p1', course_id: 'math', name: 'P1' }), useScope: () => ({ ready: true, isLoading: false, setSection: vi.fn() }) }));
vi.mock('../components/ScopePicker', () => ({ default: () => <span>Scope picker</span> }));
vi.mock('../components/ScopeStatus', () => ({ default: () => null }));

const asOf = '2026-10-02';
function assessment(id: string, values: Partial<AssessmentStat> = {}): AssessmentStat {
  return { id, title: id, kind: 'quiz', due_date: asOf, max_points: 10, graded: 3, average: 70, median: 70, min: 50, max: 90, missing_pct: 40, ...values };
}
function region(name: string) { return within(screen.getByRole('region', { name })); }
function titles(name: string) { return region(name).getAllByRole('listitem').map((item) => item.querySelector('strong')?.textContent); }

describe('assignment review evidence', () => {
  it('separates lowest scored averages from highest missing scores without changing the source order', () => {
    const rows = [assessment('No scores', { graded: 0, average: null, missing_pct: 100 }), assessment('Low average', { average: 35, missing_pct: 0, graded: 5 }), assessment('High average', { average: 90, missing_pct: 60, graded: 2 })];
    const original = structuredClone(rows);
    render(<AssessmentAnalysis rows={rows} asOf={asOf} students={5} />);
    expect(titles('Lowest graded averages')).toEqual(['Low average', 'High average']);
    expect(titles('Most missing work')).toEqual(['No scores', 'High average']);
    expect(region('Lowest graded averages').getByText('35%')).toBeInTheDocument();
    expect(region('Most missing work').getByText('100%')).toBeInTheDocument();
    expect(region('Lowest graded averages').getByText(/5 scored of 5 students/)).toBeInTheDocument();
    expect(screen.getByText(/missing scores are not counted as zero/)).toBeInTheDocument();
    expect(screen.getByText(/not question-level mistakes/)).toBeInTheDocument();
    expect(rows).toEqual(original);
  });

  it('uses the summary cutoff, including due-today work and excluding future and unavailable missing percentages', () => {
    render(<AssessmentAnalysis asOf={asOf} students={5} rows={[
      assessment('Today', { missing_pct: 20 }), assessment('Tomorrow', { due_date: '2026-10-03', missing_pct: 100 }),
      assessment('Unknown missing', { missing_pct: null }), assessment('Complete', { missing_pct: 0 }),
    ]} />);
    expect(titles('Most missing work')).toEqual(['Today']);
    expect(region('Most missing work').getByText(/through/)).toHaveTextContent(asOf);
    expect(region('Most missing work').getByText(/Due/)).toHaveTextContent(asOf);
  });

  it('preserves zero scores and extra credit and excludes ungraded or unavailable averages', () => {
    render(<AssessmentAnalysis asOf={asOf} students={5} rows={[
      assessment('Zero', { average: 0 }), assessment('Extra credit', { average: 125 }),
      assessment('Ungraded', { graded: 0 }), assessment('Unavailable', { average: null }),
    ]} />);
    expect(titles('Lowest graded averages')).toEqual(['Zero', 'Extra credit']);
    expect(region('Lowest graded averages').getByText('0%')).toBeInTheDocument();
    expect(region('Lowest graded averages').getByText('125%')).toBeInTheDocument();
  });

  it('caps each ranked list at five and breaks equal evidence by title then id', () => {
    const rows = ['g', 'f', 'e', 'd', 'c', 'b', 'a'].map((id) => assessment(id));
    render(<AssessmentAnalysis rows={rows} asOf={asOf} students={5} />);
    expect(titles('Lowest graded averages')).toEqual(['a', 'b', 'c', 'd', 'e']);
    expect(titles('Most missing work')).toEqual(['a', 'b', 'c', 'd', 'e']);
  });

  it('explains empty and not-yet-due evidence without displaying a zero average', () => {
    render(<AssessmentAnalysis asOf={asOf} students={5} rows={[assessment('Future', { graded: 0, average: null, missing_pct: null, due_date: '2026-10-03' })]} />);
    expect(screen.getByText('No graded averages to compare yet.')).toBeInTheDocument();
    expect(screen.getByText(/Future assignments are not counted as missing/)).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('updates the lists from new section/date evidence rather than retaining prior assignment data', () => {
    const { rerender } = render(<AssessmentAnalysis rows={[assessment('Original')]} asOf={asOf} students={5} />);
    rerender(<AssessmentAnalysis rows={[assessment('New section', { due_date: '2026-10-03', missing_pct: 50 })]} asOf="2026-10-03" students={10} />);
    expect(screen.queryByText('Original')).not.toBeInTheDocument();
    expect(titles('Most missing work')).toEqual(['New section']);
    expect(region('Most missing work').getByText(/3 scored of 10 students/)).toBeInTheDocument();
  });

  it('retains fractional percentages so a small missing share is not presented as zero', () => {
    render(<AssessmentAnalysis asOf={asOf} students={1000} rows={[assessment('One missing', { average: 85.6, missing_pct: 0.1, graded: 999 })]} />);
    expect(region('Most missing work').getByText('0.1%')).toBeInTheDocument();
    expect(region('Lowest graded averages').getByText('85.6%')).toBeInTheDocument();
  });

  it('does not rank missing work without a roster denominator', () => {
    render(<AssessmentAnalysis asOf={asOf} students={0} rows={[assessment('No roster', { graded: 0, average: null, missing_pct: 100 })]} />);
    expect(region('Most missing work').queryByRole('list')).not.toBeInTheDocument();
  });
});

function summary(rows: AssessmentStat[], cutoff = asOf): ClassSummary {
  return { as_of: cutoff, section_id: 'p1', section: 'P1', course: 'Math', students: 5, unknown: 0, on_track: 5, watch: 0, at_risk: 0, average: 70, distribution: { C: 5 }, assessments: rows, attention: [], attendance: [], attendance_rate: null };
}

it('renders analysis in the actual Reports page from its existing summary without adding requests', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(['report-summary', 'p1'], summary([assessment('Review this assignment')]));
  qc.setQueryData(['school-calendar'], { today: asOf, timezone: 'America/Los_Angeles' });
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.startsWith('/students/page?')) return { items: [], next_cursor: null, as_of: asOf, total_scoped: 5, total_matches: 0 };
    throw new Error(`Unexpected new request: ${path}`);
  });
  render(<QueryClientProvider client={qc}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>);
  expect(screen.getByRole('region', { name: 'Assessment review' })).toBeInTheDocument();
  expect(titles('Lowest graded averages')).toEqual(['Review this assignment']);
  await screen.findByText('No students match this search.');
  expect(vi.mocked(api).mock.calls).toHaveLength(1);
  expect(vi.mocked(api).mock.calls[0][0]).toMatch(/^\/students\/page\?/);
});

it('keeps previous analysis and cutoff on refresh failure, then updates from a successful existing summary', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(['report-summary', 'p1'], summary([assessment('Previous evidence')]));
  qc.setQueryData(['school-calendar'], { today: asOf, timezone: 'America/Los_Angeles' });
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.startsWith('/students/page?')) return { items: [], next_cursor: null, as_of: asOf, total_scoped: 5, total_matches: 0 };
    if (path.includes('/summary')) throw new Error('Summary refresh failed');
    throw new Error(`Unexpected new request: ${path}`);
  });
  render(<QueryClientProvider client={qc}><MemoryRouter><Reports /></MemoryRouter></QueryClientProvider>);
  await act(async () => { qc.setQueryData(['school-calendar'], { today: '2026-10-03', timezone: 'America/Los_Angeles' }); });
  await screen.findByText('Summary refresh failed');
  expect(titles('Most missing work')).toEqual(['Previous evidence']);
  expect(region('Most missing work').getByText(/through/)).toHaveTextContent(asOf);
  await act(async () => { qc.setQueryData(['report-summary', 'p1'], summary([assessment('Updated evidence', { due_date: '2026-10-03' })], '2026-10-03')); });
  await waitFor(() => expect(titles('Most missing work')).toEqual(['Updated evidence']));
  expect(region('Most missing work').getByText(/through/)).toHaveTextContent('2026-10-03');
});
