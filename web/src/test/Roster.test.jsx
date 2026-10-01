import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', async (orig) => ({ ...(await orig()), api: vi.fn() }));
vi.mock('../scope', () => ({
  useScope: () => ({ courses: [], course: null, section: null, sections: [], allSections: [], setCourse() {}, setSection() {} }),
}));

import { api } from '../api';
import Roster from '../pages/Roster';
import { ToastProvider } from '../components/Toast';

const S = (id, name, risk, average, extra = {}) => ({ id, name, risk, average, letter: 'B', grade_level: 9, course: 'Algebra', section: 'P1', trend: 0, attendance_rate: 95, homework_rate: 90, ...extra });
const DATA = [S('1', 'Cara', 'on_track', 91), S('2', 'Ben', 'at_risk', 55), S('3', 'Abe', 'watch', 72), S('4', 'Dee', 'on_track', null)];

const Loc = () => { const l = useLocation(); return <output data-testid="loc">{l.search}</output>; };
const renderRoster = (url = '/roster') => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ToastProvider><MemoryRouter initialEntries={[url]}><Roster /><Loc /></MemoryRouter></ToastProvider>
  </QueryClientProvider>,
);
const names = () => screen.getAllByRole('row').slice(1).map((r) => within(r).queryByRole('link')?.textContent);

beforeEach(() => { api.mockReset(); api.mockResolvedValue(DATA); });

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
    api.mockResolvedValue([]);
    renderRoster();
    expect(await screen.findByText('No students yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Add student' })).toBeInTheDocument();
  });
});
