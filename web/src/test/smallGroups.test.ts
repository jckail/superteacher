import { expect, it } from 'vitest';
import { buildSmallGroups, suggestReteachSlots } from '../smallGroups';
import type { AssessmentOut, Gradebook, GradebookRow } from '../types';
const assignment = (id: string, max_points = 10, due_date = '2026-10-02'): AssessmentOut => ({ id, section_id: 's', title: 'Same title', kind: 'quiz', max_points, due_date });
const row = (student_id: string, points: GradebookRow['points']): GradebookRow => ({ student_id, name: 'Same name', points, average: null, letter: null });
const gb = (assessments: AssessmentOut[], rows: GradebookRow[]): Gradebook => ({ as_of: '2026-10-02', section: { id: 's', name: 'Period 1', course_id: 'c' }, assessments, rows });
it('groups only explicit null due cells, preserving duplicate labels and scored zero', () => {
  const data = gb([assignment('a'), assignment('future', 10, '2026-10-03')], [row('one', { a: null, future: null }), row('two', { a: 0, future: null }), row('three', { a: null, future: null }), row('unknown', {})]);
  const result = buildSmallGroups(data, 's', { type: 'unscored', assessmentId: 'a' }, 1);
  expect(result.groups.map(group => group.members.map(member => member.studentId))).toEqual([['one'], ['three']]);
  expect(result.groups[0].members[0].evidence[0].points).toBeNull();
  expect(result.withoutEvidence).toBe(1);
  expect(buildSmallGroups(data, 's', { type: 'unscored', assessmentId: 'future' }, 4).groups).toEqual([]);
});
it('uses weighted graded category scores, excludes null/future evidence and preserves extra credit', () => {
  const data = gb([assignment('small'), assignment('large', 90), assignment('future', 100, '2026-10-03')], [row('weighted-90', { small: 0, large: 90, future: 0 }), row('weak-zero', { small: 0, large: null, future: 100 }), row('extra', { small: 20, large: 90, future: 0 }), row('none', { small: null, large: null, future: 0 })]);
  const result = buildSmallGroups(data, 's', { type: 'weak', kind: 'quiz', below: 95 }, 4);
  expect(result.groups[0].members.map(member => [member.studentId, member.percentage])).toEqual([['weak-zero', 0], ['weighted-90', 90]]);
  expect(result.groups[0].members[0].evidence.map(score => score.assessmentId)).toEqual(['small']);
  expect(result.withoutEvidence).toBe(1);
  expect(buildSmallGroups(data, 's', { type: 'weak', kind: 'quiz', below: 90 }, 4).groups[0].members.map(member => member.studentId)).toEqual(['weak-zero']);
});
it('does not overflow raw sums when valid huge scores have finite weighted percentages', () => {
  const data = gb([assignment('a', 1e308), assignment('b', 1e308)], [row('huge', { a: 5e307, b: 5e307 })]);
  expect(buildSmallGroups(data, 's', { type: 'weak', kind: 'quiz', below: 60 }, 4).groups[0].members[0].percentage).toBe(50);
});
it('never mixes sections, duplicate IDs, invalid totals or invalid score evidence', () => {
  const data = gb([assignment('a')], [row('one', { a: 0 })]);
  expect(buildSmallGroups(data, 'other', { type: 'weak', kind: 'quiz', below: 70 }, 4).groups).toEqual([]);
  for (const bad of [NaN, Infinity, -1]) expect(buildSmallGroups(gb([assignment('a')], [row('one', { a: bad })]), 's', { type: 'weak', kind: 'quiz', below: 70 }, 4).error).not.toBeNull();
  expect(buildSmallGroups(gb([assignment('a', 0)], data.rows), 's', { type: 'weak', kind: 'quiz', below: 70 }, 4).error).not.toBeNull();
  expect(buildSmallGroups(gb([assignment('a')], [row('one', { a: 0 }), row('one', { a: 1 })]), 's', { type: 'weak', kind: 'quiz', below: 70 }, 4).error).not.toBeNull();
});
it('suggests sequential teacher-chosen slots without accepting invalid dates/times or rolling into another day', () => {
  expect(suggestReteachSlots('2026-10-05', '09:10', 15, 2)).toEqual([{ date: '2026-10-05', start: '09:10', end: '09:25' }, { date: '2026-10-05', start: '09:25', end: '09:40' }]);
  for (const [date, time] of [['2026-02-30', '09:00'], ['2026-99-01', '09:00'], ['2026-10-05', '25:00'], ['2026-10-05', '23:50']]) expect(suggestReteachSlots(date, time, 15, 2)).toBeNull();
});
