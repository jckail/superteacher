import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FocusEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { AssessmentKind, Gradebook } from '../types';
import { buildSmallGroups, suggestReteachSlots } from '../smallGroups';
import type { ReteachSlot } from '../smallGroups';

interface Props { gradebook: Gradebook; sectionId: string; schoolDay: string | null; settled: boolean; calendarRefreshing?: boolean; schoolTimezone?: string | null }
const kinds: AssessmentKind[] = ['quiz', 'test', 'homework', 'project'];
const percent = (value: number) => { const rounded = Number(value.toFixed(1)); return `${rounded === value ? '' : '≈'}${rounded}%`; };

/** Suggestions only: the parent must gate current reads and pending score mutations. */
export default function SmallGroupBuilder({ gradebook, sectionId, schoolDay, settled, calendarRefreshing = false, schoolTimezone = null }: Props) {
  const client = useQueryClient();
  const identity = useMemo(() => ({ gradebook, sectionId, schoolDay, schoolTimezone, settled, client }), [gradebook, sectionId, schoolDay, schoolTimezone, settled, client]);
  const container = useRef<HTMLElement>(null);
  type ReviewedFocus = { identity: typeof identity; index: number; tag: string; type: string | null };
  const lastFocus = useRef<ReviewedFocus | null>(null);
  const suspendedFocus = useRef<ReviewedFocus | null>(null);
  const rememberFocus = (event: FocusEvent<HTMLElement>) => {
    const controls = [...(container.current?.querySelectorAll<HTMLElement>('input,select,button,summary') ?? [])];
    const index = controls.indexOf(event.target);
    if (index >= 0) lastFocus.current = { identity, index, tag: event.target.tagName, type: event.target.getAttribute('type') };
  };
  useEffect(() => {
    const clear = () => { lastFocus.current = null; suspendedFocus.current = null; };
    const outside = (event: Event) => {
      if (event.type === 'focusin' && (event.target === document.body || event.target === document.documentElement)) return;
      if (event.target instanceof Node && !container.current?.contains(event.target)) clear();
    };
    document.addEventListener('focusin', outside);
    document.addEventListener('pointerdown', outside);
    window.addEventListener('blur', clear);
    return () => { document.removeEventListener('focusin', outside); document.removeEventListener('pointerdown', outside); window.removeEventListener('blur', clear); };
  }, []);
  useLayoutEffect(() => {
    if (calendarRefreshing) {
      suspendedFocus.current = lastFocus.current?.identity === identity ? lastFocus.current : null;
      return;
    }
    const previous = suspendedFocus.current;
    suspendedFocus.current = null;
    if (!previous || previous.identity !== identity || (document.activeElement !== document.body && document.activeElement !== document.documentElement)) return;
    const control = container.current?.querySelectorAll<HTMLElement>('input,select,button,summary')[previous.index];
    if (control?.tagName === previous.tag && control.getAttribute('type') === previous.type) control.focus({ preventScroll: true });
  }, [calendarRefreshing, identity]);
  const due = gradebook.assessments.filter(a => a.section_id === sectionId && a.due_date <= gradebook.as_of);
  const defaults = () => ({ identity, mode: 'unscored' as 'unscored' | 'weak', assessmentId: due[0]?.id ?? '', kind: 'quiz' as AssessmentKind, below: 70, size: 4, selected: [] as string[], date: schoolDay ?? '', start: '', minutes: 15, plan: null as ReteachSlot[] | null });
  const [state, setState] = useState(defaults);
  // Changed evidence, scope, session, calendar context or a hard gate invalidates the review.
  // An in-flight calendar check hides actions without discarding unchanged evidence.
  const current = state.identity === identity ? state : defaults();
  useEffect(() => { setState({ identity, mode: 'unscored', assessmentId: gradebook.assessments.find(a => a.section_id === sectionId && a.due_date <= gradebook.as_of)?.id ?? '', kind: 'quiz', below: 70, size: 4, selected: [], date: schoolDay ?? '', start: '', minutes: 15, plan: null }); }, [identity, gradebook, sectionId, schoolDay]);
  const fresh = settled && Boolean(schoolDay) && gradebook.as_of === schoolDay && gradebook.section.id === sectionId;
  if (!fresh || calendarRefreshing) return <section ref={container} onFocusCapture={rememberFocus} className="card" aria-label="Small-group builder"><h2>Small-group builder</h2><p role="status">{fresh && calendarRefreshing ? 'Checking the school day before choosing groups. Your review will return if the school day, time zone and evidence are unchanged.' : 'Refresh the selected section’s gradebook and wait for score changes to finish before choosing groups.'}</p></section>;
  const criterion = current.mode === 'unscored' ? { type: 'unscored' as const, assessmentId: current.assessmentId } : { type: 'weak' as const, kind: current.kind, below: current.below };
  const result = buildSmallGroups(gradebook, sectionId, criterion, current.size);
  const selected = result.groups.filter(group => current.selected.includes(group.id));
  const slots = current.date >= (schoolDay ?? '') ? suggestReteachSlots(current.date, current.start, current.minutes, selected.length) : null;
  const change = (values: Partial<typeof state>, membership = false) => setState({ ...current, ...values, selected: membership ? [] : (values.selected ?? current.selected), plan: null });
  return <section ref={container} onFocusCapture={rememberFocus} className="card" aria-label="Small-group builder" style={{ overflowWrap: 'anywhere' }}>
    <h2>Small-group builder</h2>
    <p>Review recorded evidence, then choose groups for reteaching. Unscored work does not establish that a student failed to submit it.</p>
    <p className="muted">{gradebook.section.name} · evidence through {gradebook.as_of}</p>
    <p className="muted">Changes to scores, the section or school day clear selections and suggestions.</p>
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))' }}>
      <label>Group by <select className="input" value={current.mode} onChange={e => change({ mode: e.target.value as typeof state.mode }, true)}><option value="unscored">Shared unscored assignment</option><option value="weak">Weak assignment type</option></select></label>
      {current.mode === 'unscored' ? <label>Due assignment <select className="input" value={current.assessmentId} onChange={e => change({ assessmentId: e.target.value }, true)}>{due.length ? due.map((a, i) => <option key={a.id} value={a.id}>{i + 1}. {a.title} · {a.kind} · due {a.due_date}</option>) : <option value="">No due assignments</option>}</select></label> : <>
        <label>Assignment type <select className="input" value={current.kind} onChange={e => change({ kind: e.target.value as AssessmentKind }, true)}>{kinds.map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label>
        <label>Below (%) <input className="input" type="number" min={0} max={100} value={Number.isNaN(current.below) ? '' : current.below} onChange={e => change({ below: e.target.value === '' ? NaN : Number(e.target.value) }, true)} /></label>
      </>}
      <label>Maximum students per group <input className="input" type="number" min={1} max={12} value={Number.isNaN(current.size) ? '' : current.size} onChange={e => change({ size: e.target.value === '' ? NaN : Number(e.target.value) }, true)} /></label>
    </div>
    {result.error && <p role="status">{result.error}</p>}
    {!result.error && !result.groups.length && <p>No students match this evidence.</p>}
    {result.withoutEvidence > 0 && <p>{result.withoutEvidence} {result.withoutEvidence === 1 ? 'student lacks' : 'students lack'} enough score evidence for this choice and {result.withoutEvidence === 1 ? 'is' : 'are'} excluded.</p>}
    {current.mode === 'weak' && <p className="muted">Percentages weight each graded assignment by its possible points. Unscored and future work are excluded; extra credit is preserved. Membership uses unrounded percentages; ≈ marks rounded values.</p>}
    {result.groups.map((group, index) => <div key={group.id} role="group" aria-label={`Suggested group ${index + 1}`}>
      <h3>Group {index + 1} · {group.label}</h3>
      <label><input type="checkbox" checked={current.selected.includes(group.id)} onChange={e => change({ selected: e.target.checked ? [...current.selected, group.id] : current.selected.filter(id => id !== group.id) })} /> Include group {index + 1} in suggested plan</label>
      <ul>{group.members.map(member => <li key={member.studentId}>{member.name}{member.percentage === null ? ' · unscored' : ` · ${percent(member.percentage)}`}</li>)}</ul>
      <details><summary>Recorded evidence for group {index + 1}</summary>{group.members.map(member => <div key={member.studentId}><strong>{member.name}</strong><ul>{member.evidence.map(score => <li key={score.assessmentId}>{score.title} · due {score.dueDate} · {score.points === null ? 'unscored' : `${score.points} / ${score.maxPoints}`}</li>)}</ul></div>)}</details>
    </div>)}
    {result.groups.length > 0 && <>
      <h3>Suggest reteach slots</h3><p>Choose an available school date and start time. These suggestions stay on this page and do not reserve time.</p>
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))' }}>
        <label>Reteach date <input className="input" type="date" min={schoolDay ?? undefined} value={current.date} onChange={e => change({ date: e.target.value })} /></label>
        <label>Available start time (school time) <input className="input" type="time" value={current.start} onChange={e => change({ start: e.target.value })} /></label>
        <label>Minutes per group <input className="input" type="number" min={5} max={60} value={Number.isNaN(current.minutes) ? '' : current.minutes} onChange={e => change({ minutes: e.target.value === '' ? NaN : Number(e.target.value) })} /></label>
      </div>
      {selected.length > 0 && !slots && <p role="status">Choose a valid date, start time and duration that fit within one day.</p>}
      <button className="btn" type="button" disabled={!slots || Boolean(result.error)} onClick={() => { if (slots) setState({ ...current, plan: slots }); }}>Suggest reteach slots</button>
      {current.plan && <div role="region" aria-label="Suggested reteach plan"><h3>Suggested plan</h3><ol>{current.plan.map((slot, i) => <li key={selected[i].id}>{slot.date} · {slot.start}–{slot.end} · {selected[i].members.map(member => member.name).join(', ')}</li>)}</ol><p>Adjust the settings and regenerate before using this plan.</p></div>}
    </>}
  </section>;
}
