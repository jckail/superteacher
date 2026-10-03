import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, fmt } from '../api';
import { ToastProvider } from '../components/Toast';
import Gradebook from '../pages/Gradebook';
import type { Gradebook as GradebookData } from '../types';

vi.mock('../api', async (original) => ({ ...(await original<typeof import('../api')>()), api: vi.fn() }));
vi.mock('../scope', () => ({
  useActiveSection: () => ({ id: 'class', course_id: 'course', name: 'Synthetic class' }),
  useScope: () => ({ ready: true, isLoading: false }),
}));
vi.mock('../components/ScopePicker', () => ({ default: () => null }));
vi.mock('../components/SmallGroupBuilder', () => ({ default: () => null }));

beforeEach(() => { vi.mocked(api).mockReset(); });

it.each([
  { values: [1e308, 1e308], expected: 1e308 },
  { values: [Number.MAX_VALUE, Number.MAX_VALUE, Number.MAX_VALUE], expected: Number.MAX_VALUE },
  { values: [10, 90], expected: 50 },
  { values: [0, null], expected: 0 },
  { values: [null, null], expected: null },
])('renders finite class and assignment means for $values', async ({ values, expected }) => {
  const gradebook: GradebookData = {
    as_of: '2026-10-02', section: { id: 'class', course_id: 'course', name: 'Synthetic class' },
    assessments: [{ id: 'work', section_id: 'class', title: 'Due work', kind: 'test', max_points: 100, due_date: '2026-10-02' }],
    rows: values.map((value, index) => ({ student_id: `student${index}`, name: `Synthetic ${index}`, average: value, letter: value == null ? null : 'A', points: { work: value } })),
  };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/calendar') return { timezone: 'America/Los_Angeles', today: '2026-10-02' };
    if (path === '/sections/class/gradebook') return gradebook;
    throw new Error(`Unexpected fixture request: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  render(<QueryClientProvider client={client}><ToastProvider><MemoryRouter><Gradebook /></MemoryRouter></ToastProvider></QueryClientProvider>);
  const footer = (await screen.findByText('Class average')).closest('tr');
  expect(footer).not.toBeNull();
  const cells = within(footer!).getAllByRole('cell');
  expect(cells[1]).toHaveTextContent(fmt(expected, '%'));
  expect(cells[2]).toHaveTextContent(fmt(expected, '%'));
  expect(footer).not.toHaveTextContent(/Infinity|NaN/);
  client.clear();
});
