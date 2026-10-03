import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import SmallGroupBuilder from '../components/SmallGroupBuilder';
import type { Gradebook } from '../types';
const data: Gradebook = { as_of: '2026-10-02', section: { id: 's', name: 'Period 1', course_id: 'c' }, assessments: [
  { id: 'a', section_id: 's', title: 'Quiz', kind: 'quiz', due_date: '2026-10-02', max_points: 10 },
  { id: 'b', section_id: 's', title: 'Quiz', kind: 'quiz', due_date: '2026-10-02', max_points: 90 },
  { id: 'future', section_id: 's', title: 'Future', kind: 'quiz', due_date: '2026-10-03', max_points: 100 },
], rows: [
  { student_id: 'ada', name: 'Ada', average: null, letter: null, points: { a: null, b: null, future: null } },
  { student_id: 'bea', name: 'Bea', average: null, letter: null, points: { a: null, b: 90, future: null } },
  { student_id: 'zero', name: 'Zero', average: 0, letter: 'F', points: { a: 0, b: null, future: null } },
  { student_id: 'weighted', name: 'Weighted', average: 90, letter: 'A', points: { a: 0, b: 90, future: 0 } },
] };
afterEach(() => vi.restoreAllMocks());
function setup() {
  let client = new QueryClient();
  let props = { gradebook: data, sectionId: 's', schoolDay: '2026-10-02' as string | null, settled: true };
  const tree = () => <QueryClientProvider client={client}><SmallGroupBuilder {...props} /></QueryClientProvider>;
  const view = render(tree());
  return { user: userEvent.setup(), update: (next: Partial<typeof props>) => { props = { ...props, ...next }; view.rerender(tree()); }, replaceClient: () => { client = new QueryClient(); view.rerender(tree()); } };
}
const group = (index = 1) => within(screen.getByRole('group', { name: `Suggested group ${index}` }));
const planButton = () => screen.getByRole('button', { name: 'Suggest reteach slots' });
async function planned(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox', { name: 'Include group 1 in suggested plan' }));
  fireEvent.change(screen.getByLabelText('Reteach date'), { target: { value: '2026-10-05' } });
  fireEvent.change(screen.getByLabelText('Available start time (school time)'), { target: { value: '09:10' } });
  await user.click(planButton());
  expect(screen.getByRole('region', { name: 'Suggested reteach plan' })).toBeInTheDocument();
}
it('presents due explicit unscored membership and distinguishes duplicate assignment labels by IDs', async () => {
  const { user } = setup();
  expect(group().getByText('Ada · unscored')).toBeInTheDocument();
  expect(group().getByText('Bea · unscored')).toBeInTheDocument();
  expect(group().queryByText('Zero · unscored')).not.toBeInTheDocument();
  expect(screen.queryByRole('option', { name: /Future/ })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Due assignment'), 'b');
  expect(group().getByText('Zero · unscored')).toBeInTheDocument();
  expect(group().queryByText('Bea · unscored')).not.toBeInTheDocument();
});
it('shows weighted zero evidence without assigning unscored or genuinely strong category students', async () => {
  const { user } = setup(); await user.selectOptions(screen.getByLabelText('Group by'), 'weak');
  expect(group().getByText('Zero · 0%')).toBeInTheDocument();
  expect(group().queryByText(/Weighted/)).not.toBeInTheDocument();
  expect(screen.getByText(/1 student lacks enough score evidence/)).toBeInTheDocument();
  await user.click(group().getByText('Recorded evidence for group 1'));
  expect(group().getByText('Quiz · due 2026-10-02 · 0 / 10')).toBeInTheDocument();
});
it('requires teacher-chosen availability and produces only local suggestions without network writes', async () => {
  const network = vi.spyOn(globalThis, 'fetch'); const { user } = setup();
  expect(planButton()).toBeDisabled();
  await planned(user);
  expect(screen.getByRole('region', { name: 'Suggested reteach plan' })).toHaveTextContent('2026-10-05 · 09:10–09:25 · Ada, Bea');
  expect(network).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Minutes per group'), { target: { value: '20' } });
  expect(screen.queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
});
it('splits groups to the requested capacity and assigns sequential suggested slots', async () => {
  const { user } = setup(); fireEvent.change(screen.getByLabelText('Maximum students per group'), { target: { value: '1' } });
  await user.click(screen.getByRole('checkbox', { name: 'Include group 1 in suggested plan' }));
  await user.click(screen.getByRole('checkbox', { name: 'Include group 2 in suggested plan' }));
  fireEvent.change(screen.getByLabelText('Available start time (school time)'), { target: { value: '09:10' } });
  await user.click(planButton());
  const plan = screen.getByRole('region', { name: 'Suggested reteach plan' });
  expect(plan).toHaveTextContent('09:10–09:25 · Ada'); expect(plan).toHaveTextContent('09:25–09:40 · Bea');
});
it('drops selections and reviewed plan after evidence changes and does not revive them on restoration', async () => {
  const { user, update } = setup(); await planned(user);
  update({ gradebook: { ...data, rows: data.rows.map(row => row.student_id === 'ada' ? { ...row, points: { ...row.points, a: 0 } } : row) } });
  expect(screen.queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
  update({ gradebook: data });
  expect(screen.getByRole('checkbox', { name: 'Include group 1 in suggested plan' })).not.toBeChecked();
});
it('hides action/evidence for unresolved section, stale cutoff and pending optimistic score changes', () => {
  const { update } = setup();
  for (const changes of [{ sectionId: 'wrong' }, { sectionId: 's', schoolDay: '2026-10-03' }, { schoolDay: '2026-10-02', settled: false }, { schoolDay: null, settled: true }]) {
    update(changes); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Refresh the selected section');
  }
});
it('requires new selections after the mutation gate closes and after session replacement', async () => {
  const { user, update, replaceClient } = setup(); await planned(user);
  update({ settled: false }); update({ settled: true });
  expect(screen.getByRole('checkbox', { name: 'Include group 1 in suggested plan' })).not.toBeChecked();
  await planned(user); replaceClient();
  expect(screen.queryByRole('region', { name: 'Suggested reteach plan' })).not.toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: 'Include group 1 in suggested plan' })).not.toBeChecked();
});
it('refuses invalid group capacity, past date and slots spilling into tomorrow', async () => {
  const { user } = setup();
  fireEvent.change(screen.getByLabelText('Maximum students per group'), { target: { value: '' } });
  expect(screen.getByRole('status')).toHaveTextContent('Choose a group size from 1 to 12');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Maximum students per group'), { target: { value: '4' } });
  await user.click(screen.getByRole('checkbox', { name: 'Include group 1 in suggested plan' }));
  fireEvent.change(screen.getByLabelText('Reteach date'), { target: { value: '2026-10-01' } });
  fireEvent.change(screen.getByLabelText('Available start time (school time)'), { target: { value: '09:00' } });
  expect(planButton()).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Reteach date'), { target: { value: '2026-10-02' } });
  fireEvent.change(screen.getByLabelText('Available start time (school time)'), { target: { value: '23:50' } });
  expect(planButton()).toBeDisabled();
});

it('marks rounded weak-type percentages without changing exact threshold membership', async () => {
  const { user, update } = setup();
  update({ gradebook: { ...data, assessments: [{ ...data.assessments[0], max_points: 300 }], rows: [
    { student_id: 'boundary', name: 'Boundary', average: null, letter: null, points: { a: 209.9 } },
    { student_id: 'exact', name: 'Exact', average: null, letter: null, points: { a: 210 } },
    { student_id: 'zero', name: 'Zero', average: 0, letter: 'F', points: { a: 0 } },
    { student_id: 'bonus', name: 'Bonus', average: 125, letter: 'A', points: { a: 375 } },
  ] } });
  await user.selectOptions(screen.getByLabelText('Group by'), 'weak');
  expect(group().getByText('Boundary · ≈70%')).toBeInTheDocument();
  expect(group().getByText('Zero · 0%')).toBeInTheDocument();
  expect(group().queryByText('Exact · 70%')).not.toBeInTheDocument();
  expect(screen.getByText(/Membership uses unrounded percentages/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Below (%)'), { target: { value: '100' } });
  expect(group().getByText('Exact · 70%')).toBeInTheDocument();
  expect(group().queryByText('Bonus · 125%')).not.toBeInTheDocument();
  expect(screen.getByText(/extra credit is preserved/)).toBeInTheDocument();
});
