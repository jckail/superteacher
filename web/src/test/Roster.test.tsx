import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', async (orig) => ({ ...(await orig<typeof import('../api')>()), api: vi.fn() }));
vi.mock('../scope', () => ({
  useScope: () => ({ courses: [], course: null, section: null, sections: [], allSections: [], setCourse() {}, setSection() {} }),
}));

import type { Risk, StudentSummary } from '../types';
import { api } from '../api';
import Roster from '../pages/Roster';
import { ToastProvider } from '../components/Toast';

const S = (id: string, name: string, risk: Risk, average: number | null, extra: Partial<StudentSummary> = {}): StudentSummary => ({ id, name, risk, average, letter: 'B', grade_level: 9, course_id: 'algebra', section_id: 'p1', course: 'Algebra', section: 'P1', gpa: null, missing: 0, risk_reasons: [], trend: 0, attendance_rate: 95, homework_rate: 90, ...extra });
const DATA = [S('1', 'Cara', 'on_track', 91), S('2', 'Ben', 'at_risk', 55), S('3', 'Abe', 'watch', 72), S('4', 'Dee', 'on_track', null)];

const Loc = () => { const l = useLocation(); return <output data-testid="loc">{l.search}</output>; };
const renderRoster = (url = '/roster') => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ToastProvider><MemoryRouter initialEntries={[url]}><Roster /><Loc /></MemoryRouter></ToastProvider>
  </QueryClientProvider>,
);
const names = () => screen.getAllByRole('row').slice(1).map((r) => within(r).queryByRole('link')?.textContent);

beforeEach(() => { vi.mocked(api).mockReset(); vi.mocked(api).mockResolvedValue(DATA); });

describe('Roster', () => {
  it('lists students sorted by risk (at risk first) with real links', async () => {
    renderRoster();
    await screen.findByText('Cara');
    expect(names()).toEqual(['Ben', 'Abe', 'Cara', 'Dee']);
    expect(screen.getByRole('link', { name: 'Ben' })).toHaveAttribute('href', '/students/2');
  });

  it('sorts via keyboard-operable header buttons, empty values last, and reflects it in the URL', async () => {
    const user = userEvent.setup();
    renderRoster();
    await screen.findByText('Cara');
    await user.click(screen.getByRole('button', { name: /^Average/ }));
    expect(names()).toEqual(['Ben', 'Abe', 'Cara', 'Dee']);                       // asc, null last
    expect(screen.getByRole('columnheader', { name: /Average/ })).toHaveAttribute('aria-sort', 'ascending');
    await user.click(screen.getByRole('button', { name: /^Average/ }));
    expect(names()).toEqual(['Cara', 'Abe', 'Ben', 'Dee']);                       // desc, null still last
    expect(screen.getByTestId('loc')).toHaveTextContent('sort=average');
    expect(screen.getByTestId('loc')).toHaveTextContent('dir=desc');
  });

  it('filters by status and search, and keeps filters in the URL', async () => {
    const user = userEvent.setup();
    renderRoster();
    await screen.findByText('Cara');
    await user.click(screen.getByRole('button', { name: 'At risk' }));
    expect(names()).toEqual(['Ben']);
    expect(screen.getByRole('button', { name: 'At risk' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('loc')).toHaveTextContent('status=at_risk');
    await user.click(screen.getByRole('button', { name: 'All' }));
    await user.type(screen.getByLabelText('Search students'), 'ab');
    expect(names()).toEqual(['Abe']);
    expect(screen.getByTestId('loc')).toHaveTextContent('q=ab');
  });

  it('restores filters from the URL and can clear them', async () => {
    const user = userEvent.setup();
    renderRoster('/roster?status=on_track&q=de');
    await screen.findByText('Dee');
    expect(names()).toEqual(['Dee']);
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(names()).toHaveLength(4);
    expect(screen.getByTestId('loc')).toHaveTextContent(/^$/);
  });

  it('shows a call to action when the roster is empty', async () => {
    vi.mocked(api).mockResolvedValue([]);
    renderRoster();
    expect(await screen.findByText('No students yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Add student' })).toBeInTheDocument();
  });
  it('renders bounded pages while search and sorting apply to the entire roster', async () => {
    const user = userEvent.setup();
    vi.mocked(api).mockResolvedValue(Array.from({ length: 101 }, (_, i) => S(String(i), `Student ${String(i).padStart(3, '0')}`, 'on_track', i)));
    renderRoster('/roster?sort=name');
    await screen.findByText('Student 000');
    expect(names()).toHaveLength(50);
    expect(screen.queryByText('Student 100')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(names()[0]).toBe('Student 050');
    expect(screen.getByTestId('loc')).toHaveTextContent('page=2');
    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(names()).toEqual(['Student 100']);
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    await user.type(screen.getByRole('searchbox', { name: 'Search students' }), '000');
    expect(names()).toEqual(['Student 000']);
    expect(screen.getByTestId('loc')).not.toHaveTextContent('page=');
  });

  it('clamps invalid or out-of-range page links to valid populated pages', async () => {
    vi.mocked(api).mockResolvedValue(Array.from({ length: 51 }, (_, i) => S(String(i), `Student ${String(i).padStart(3, '0')}`, 'on_track', i)));
    renderRoster('/roster?sort=name&page=999');
    await screen.findByText('Student 050');
    expect(names()).toEqual(['Student 050']);
    expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
  });

});
