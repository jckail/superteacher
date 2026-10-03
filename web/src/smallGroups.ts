import type { AssessmentKind, AssessmentOut, Gradebook } from './types';

export type GroupCriterion = { type: 'unscored'; assessmentId: string } | { type: 'weak'; kind: AssessmentKind; below: number };
export interface GroupEvidence { assessmentId: string; title: string; dueDate: string; points: number | null; maxPoints: number }
export interface GroupMember { studentId: string; name: string; percentage: number | null; evidence: GroupEvidence[] }
export interface SmallGroup { id: string; label: string; members: GroupMember[] }
export interface GroupResult { groups: SmallGroup[]; withoutEvidence: number; error: string | null }
const unavailable = (error: string): GroupResult => ({ groups: [], withoutEvidence: 0, error });
const validMaximum = (assessment: AssessmentOut) => Number.isFinite(assessment.max_points) && assessment.max_points > 0;

/** Pure, section-scoped suggestions. Explicitly unscored cells never become scored zeroes. */
export function buildSmallGroups(gradebook: Gradebook, sectionId: string, criterion: GroupCriterion, size: number): GroupResult {
  if (gradebook.section.id !== sectionId) return unavailable('Refresh the gradebook for the selected section.');
  if (!Number.isInteger(size) || size < 1 || size > 12) return unavailable('Choose a group size from 1 to 12.');
  if (criterion.type === 'weak' && (!Number.isFinite(criterion.below) || criterion.below < 0 || criterion.below > 100)) return unavailable('Choose a threshold from 0% to 100%.');
  if (new Set(gradebook.assessments.map(a => a.id)).size !== gradebook.assessments.length || new Set(gradebook.rows.map(row => row.student_id)).size !== gradebook.rows.length || gradebook.assessments.some(a => a.section_id !== sectionId)) return unavailable('The gradebook evidence changed. Refresh before grouping.');
  const assessments = gradebook.assessments.filter(a => a.due_date <= gradebook.as_of && (criterion.type === 'unscored' ? a.id === criterion.assessmentId : a.kind === criterion.kind));
  if (criterion.type === 'unscored' && !assessments.length) return unavailable('Choose a current assignment due by the summary date.');
  if (assessments.some(a => !validMaximum(a))) return unavailable('Some assignment totals cannot be used. Refresh the gradebook.');
  const members: GroupMember[] = [];
  let withoutEvidence = 0;
  for (const row of gradebook.rows) {
    const evidence: GroupEvidence[] = [];
    let unknownCell = false;
    for (const assessment of assessments) {
      const points = row.points[assessment.id];
      if (points === undefined) { unknownCell = true; continue; }
      if (points !== null && (!Number.isFinite(points) || points < 0 || !Number.isFinite(points / assessment.max_points * 100))) return unavailable('Some recorded scores cannot be used. Refresh the gradebook.');
      if (criterion.type === 'unscored' ? points === null : points !== null) evidence.push({ assessmentId: assessment.id, title: assessment.title, dueDate: assessment.due_date, points, maxPoints: assessment.max_points });
    }
    if (unknownCell || !evidence.length) {
      // Scored work is not eligible for an unscored group; only unknown cells lack evidence there.
      if (unknownCell || criterion.type === 'weak') withoutEvidence += 1;
      continue;
    }
    let percentage: number | null = null;
    if (criterion.type === 'weak') {
      // Normalize weights before summing: raw point/maxima sums can overflow despite finite percentages.
      const scale = evidence.reduce((maximum, score) => Math.max(maximum, score.maxPoints), 0);
      const weight = evidence.reduce((total, score) => total + score.maxPoints / scale, 0);
      const totalMaximum = evidence.reduce((total, score) => total + score.maxPoints, 0);
      percentage = Number.isFinite(totalMaximum)
        ? evidence.reduce((total, score) => total + score.points! / totalMaximum * 100, 0)
        : evidence.reduce((total, score) => total + (score.points! / score.maxPoints * 100) * (score.maxPoints / scale / weight), 0);
      if (!Number.isFinite(percentage)) return unavailable('The recorded score totals cannot be used. Refresh the gradebook.');
      if (percentage >= criterion.below) continue;
    }
    members.push({ studentId: row.student_id, name: row.name, percentage, evidence });
  }
  members.sort((a, b) => a.name.localeCompare(b.name) || a.studentId.localeCompare(b.studentId));
  const label = criterion.type === 'unscored' ? `Unscored: ${assessments[0].title}` : `${criterion.kind} below ${criterion.below}%`;
  const groups: SmallGroup[] = [];
  for (let offset = 0; offset < members.length; offset += size) {
    const batch = members.slice(offset, offset + size);
    groups.push({ id: JSON.stringify([criterion, batch.map(member => member.studentId)]), label, members: batch });
  }
  return { groups, withoutEvidence, error: null };
}

export interface ReteachSlot { date: string; start: string; end: string }
/** Times are teacher-chosen local clock values; this neither reserves nor infers calendar availability. */
export function suggestReteachSlots(date: string, start: string, minutes: number, count: number): ReteachSlot[] | null {
  const timestamp = Date.parse(`${date}T12:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0, 10) !== date || !/^\d{2}:\d{2}$/.test(start) || !Number.isInteger(minutes) || minutes < 5 || minutes > 60 || !Number.isInteger(count) || count < 1) return null;
  const [hour, minute] = start.split(':').map(Number);
  if (hour > 23 || minute > 59) return null;
  const begin = hour * 60 + minute;
  if (begin + minutes * count >= 24 * 60) return null;
  const clock = (value: number) => `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
  return Array.from({ length: count }, (_, i) => ({ date, start: clock(begin + i * minutes), end: clock(begin + (i + 1) * minutes) }));
}
