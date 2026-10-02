import type { ChangeEvent, KeyboardEvent, AriaAttributes } from 'react';
import type { AssessmentKind, AssessmentOut, AssessmentPatch, Gradebook as GradebookData, GradebookRow } from '../types';
import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api';
import { useActiveSection, useScope } from '../scope';
import ScopePicker from '../components/ScopePicker';
import ScopeStatus from '../components/ScopeStatus';
import { useToast } from '../components/Toast';
import { useSchoolCalendar } from '../schoolCalendar';
import { EmptyState, ErrorBox, Loading, Modal, gradeColor } from '../components/ui';

type Direction = 'up' | 'down';
interface ScoreCellProps { value: number | null; max?: number; onSave: (points: number | null) => unknown; label: string; onNav?: (direction: Direction, cell: string) => boolean; cell?: string }
interface ScoreChange { aid: string; student_id: string; points: number | null; name: string; title: string; sectionId: string }
interface AssessmentForm { title: string; kind: AssessmentKind; max_points: string; due_date: string }

export function NewAssessment({ sectionId, schoolDay, onClose }: { sectionId: string; schoolDay: string; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState<AssessmentForm>({ title: '', kind: 'homework', max_points: '10', due_date: schoolDay });
  const set = (k: keyof AssessmentForm) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const value = e.target.value;
    if (k === 'kind') {
      if (value === 'homework' || value === 'quiz' || value === 'test' || value === 'project') setF((p) => ({ ...p, kind: value }));
    } else setF((p) => ({ ...p, [k]: value }));
  };
  const create = useMutation({
    mutationFn: () => api<GradebookData>(`/sections/${sectionId}/assessments`, { method: 'POST', body: { ...f, title: f.title.trim(), max_points: Number(f.max_points) } }),
    onSuccess: (gb) => { qc.setQueryData(['gradebook', sectionId], gb); qc.invalidateQueries(); toast.success(`Added “${f.title.trim()}”`); onClose(); },
  });
  const maximum = Number(f.max_points);
  const valid = Boolean(f.title.trim() && f.due_date && Number.isFinite(maximum) && maximum > 0 && maximum <= 1_000_000);
  const close = () => { if (!create.isPending) onClose(); };
  return (
    <Modal title="New assignment" onClose={close}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); if (valid && !create.isPending) create.mutate(); }}>
        <label className="field">Title<input className="input" required autoFocus maxLength={120} disabled={create.isPending} value={f.title} onChange={set('title')} /></label>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>Type<select className="input" disabled={create.isPending} value={f.kind} onChange={set('kind')}>{['homework', 'quiz', 'test', 'project'].map((k) => <option key={k}>{k}</option>)}</select></label>
          <label className="field" style={{ width: 110 }}>Max points<input className="input" type="number" required min="0" max="1000000" step="any" disabled={create.isPending} value={f.max_points} onChange={set('max_points')} /></label>
        </div>
        <label className="field">Due<input className="input" type="date" required disabled={create.isPending} value={f.due_date} onChange={set('due_date')} /></label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" disabled={create.isPending} onClick={close}>Cancel</button><button className="btn primary" disabled={create.isPending || !valid}>Create</button></div>
      </form>
    </Modal>
  );
}

export function EditAssessment({ assessment, onClose }: { assessment: AssessmentOut; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<AssessmentForm>({ title: assessment.title, kind: assessment.kind, max_points: String(assessment.max_points), due_date: assessment.due_date });
  const max = Number(form.max_points);
  const valid = Boolean(form.title.trim() && form.due_date && Number.isFinite(max) && max > 0 && max <= 1_000_000);
  const changed = form.title.trim() !== assessment.title || form.kind !== assessment.kind || max !== assessment.max_points || form.due_date !== assessment.due_date;
  const save = useMutation({
    mutationFn: () => {
      const body: AssessmentPatch = { title: form.title.trim(), kind: form.kind, max_points: max, due_date: form.due_date };
      return api<GradebookData>(`/assessments/${assessment.id}`, { method: 'PATCH', body });
    },
    onSuccess: (gb) => {
      qc.setQueryData(['gradebook', assessment.section_id], gb);
      for (const key of ['gradebook', 'overview', 'students', 'student', 'insight', 'report-summary']) void qc.invalidateQueries({ queryKey: [key] });
      toast.success('Assignment updated'); onClose();
    },
  });
  const close = () => { if (!save.isPending) onClose(); };
  return (
    <Modal title="Edit assignment" onClose={close}>
      <form className="grid" onSubmit={(event) => { event.preventDefault(); if (valid && changed && !save.isPending) save.mutate(); }}>
        <label className="field">Title<input className="input" required autoFocus maxLength={120} value={form.title} disabled={save.isPending} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
        <label className="field">Type<select className="input" value={form.kind} disabled={save.isPending} onChange={(event) => {
          const kind = event.target.value;
          if (kind === 'homework' || kind === 'quiz' || kind === 'test' || kind === 'project') setForm({ ...form, kind });
        }}>{['homework', 'quiz', 'test', 'project'].map((kind) => <option key={kind}>{kind}</option>)}</select></label>
        <label className="field">Max points<input className="input" type="number" required min="0" max="1000000" step="any" value={form.max_points} disabled={save.isPending} onChange={(event) => setForm({ ...form, max_points: event.target.value })} /></label>
        <label className="field">Due<input className="input" type="date" required value={form.due_date} disabled={save.isPending} onChange={(event) => setForm({ ...form, due_date: event.target.value })} /></label>
        {max !== assessment.max_points && <p role="status">Changing max points keeps every student&apos;s raw score unchanged. Percentages, averages and risk indicators will be recalculated using the new maximum.</p>}
        <ErrorBox error={save.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" disabled={save.isPending} onClick={close}>Cancel</button><button className="btn primary" disabled={save.isPending || !valid || !changed}>Save assignment</button></div>
      </form>
    </Modal>
  );
}

/**
 * Edit-in-place score. Commits once on blur/Enter when the value changed and is valid;
 * Escape or a failed save puts the previous value back. Over-max scores are allowed (extra credit) but flagged.
 * `onSave(points)` may return a promise; if it rejects the draft reverts.
 */
export function ScoreCell({ value, max, onSave, label, onNav, cell = '' }: ScoreCellProps) {
  const [draft, setDraft] = useState<number | string>(value ?? '');
  const [prev, setPrev] = useState(value);
  const revision = useRef(0);
  if (prev !== value) { setPrev(value); setDraft(value ?? ''); }   // server/optimistic value changed → resync

  const text = String(draft).trim();
  const num = text === '' ? null : Number(text);
  const invalid = text !== '' && (num === null || !Number.isFinite(num) || num < 0);
  const over = !invalid && num != null && max != null && num > max;

  const commit = () => {
    if (invalid) { setDraft(value ?? ''); return; }
    if (num === value) { setDraft(value ?? ''); return; }
    const savingRevision = revision.current;
    const previousValue = value;
    // The current prop may already contain this mutation's optimistic value when it rejects.
    Promise.resolve(onSave(num)).catch(() => { if (revision.current === savingRevision) setDraft(previousValue ?? ''); });
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setDraft(value ?? ''); return; }
    const dir = e.key === 'Enter' ? 'down' : e.key === 'ArrowDown' ? 'down' : e.key === 'ArrowUp' ? 'up' : null;
    if (!dir) return;
    e.preventDefault();
    if (!onNav?.(dir, cell)) e.currentTarget.blur();   // blur → commit
  };
  return (
    <>
      <input className={`grade-input num ${value == null && text === '' ? 'missing' : ''} ${invalid ? 'invalid' : ''}`} inputMode="decimal" autoComplete="off"
        aria-label={label} aria-invalid={invalid || undefined} title={`out of ${max}`} data-cell={cell}
        value={draft} onChange={(e) => { revision.current += 1; setDraft(e.target.value); }} onBlur={commit} onKeyDown={onKeyDown} />
      {(over || invalid) && <span className="cell-warn" role="status">{invalid ? 'Enter a number ≥ 0' : `Over ${max}`}</span>}
    </>
  );
}

const mean = (xs: (number | null | undefined)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

export default function Gradebook() {
  const section = useActiveSection();
  const calendar = useSchoolCalendar(!!section);
  const { isLoading: scopeLoading, ready } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<AssessmentOut | null>(null);
  const [sort, setSort] = useState<{ key: string; dir: number }>({ key: 'name', dir: 1 });
  const wrap = useRef<HTMLDivElement>(null);
  const key = ['gradebook', section?.id];
  const q = useQuery({ queryKey: key, queryFn: ({ signal }) => api<GradebookData>(`/sections/${section?.id}/gradebook`, { signal }), enabled: !!section });

  const save = useMutation({
    mutationKey: ['gb-score'],
    scope: { id: 'gb-score' },
    mutationFn: ({ aid, student_id, points }: ScoreChange) => api<GradebookData>(`/assessments/${aid}/scores`, { method: 'PUT', body: { scores: [{ student_id, points }] } }),
    onMutate: async ({ aid, student_id, points, sectionId }) => {
      const queryKey = ['gradebook', sectionId];
      await qc.cancelQueries({ queryKey });
      const prev = qc.getQueryData<GradebookData>(queryKey);
      qc.setQueryData<GradebookData>(queryKey, (d) => d && ({ ...d, rows: d.rows.map((r) => (r.student_id === student_id ? { ...r, points: { ...r.points, [aid]: points } } : r)) }));
      return { prev, queryKey };
    },
    onError: (e, v, ctx) => {
      if (ctx?.prev) qc.setQueryData<GradebookData>(ctx.queryKey, (d) => d && ({ ...d, rows: d.rows.map((r) => (r.student_id === v.student_id && r.points[v.aid] === v.points ? { ...r, points: { ...r.points, [v.aid]: ctx.prev?.rows.find((x) => x.student_id === v.student_id)?.points[v.aid] ?? null } } : r)) }));
      toast.error(`Couldn’t save ${v.name}’s score for ${v.title}: ${e.message}`);
    },
    onSuccess: (_gb, v) => { toast.success(`Saved ${v.name} · ${v.title}`); },
    onSettled: () => {
      if (qc.isMutating({ mutationKey: ['gb-score'] }) <= 1) void qc.invalidateQueries({ queryKey: ['gradebook'] });
      for (const key of ['overview', 'students', 'student', 'insight', 'report-summary']) void qc.invalidateQueries({ queryKey: [key] });
    },
  });

  const gb = q.data;
  const rows = useMemo(() => {
    if (!gb) return [];
    const get = (r: GradebookRow) => (sort.key === 'name' ? r.name.toLowerCase() : sort.key === 'avg' ? r.average : (r.points[sort.key] ?? null));
    return [...gb.rows].sort((a, b) => {
      const [x, y] = [get(a), get(b)];
      if (x == null && y == null) return 0;
      if (x == null) return 1; if (y == null) return -1;   // empty values always last
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
    });
  }, [gb, sort]);
  const colAvg = useMemo(() => (gb ? gb.assessments.map((a) => mean(gb.rows.map((r) => { const points = r.points[a.id]; return points == null ? null : (points / a.max_points) * 100; }))) : []), [gb]);
  const toggleSort = (k: string) => setSort((s) => ({ key: k, dir: s.key === k ? -s.dir : (k === 'name' ? 1 : -1) }));

  /** Move focus to the cell above/below in the same column. Returns false at the edge. */
  const nav = (dir: Direction, cell: string) => {
    const [r, c] = cell.split(':').map(Number);
    const next = wrap.current?.querySelector<HTMLInputElement>(`[data-cell="${r + (dir === 'down' ? 1 : -1)}:${c}"]`);
    if (!next) return false;
    next.focus(); next.select?.();
    return true;
  };

  if (!ready) return <><div className="topbar"><h1>Gradebook</h1><ScopePicker /></div><ScopeStatus /></>;
  if (scopeLoading) return <Loading />;
  if (!section) return (
    <>
      <div className="topbar"><h1>Gradebook</h1><ScopePicker /></div>
      <ScopeStatus />
      <EmptyState title="No classes yet"><p>Create a course and section to start grading.</p><div className="row"><Link className="btn primary" to="/roster">Go to roster</Link></div></EmptyState>
    </>
  );
  const ind = (k: string) => (sort.key === k ? (sort.dir > 0 ? ' ↑' : ' ↓') : '');
  const aria = (k: string): AriaAttributes['aria-sort'] => (sort.key === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none');
  return (
    <>
      <div className="topbar">
        <div><h1>Gradebook</h1><div className="page-sub">{section.name} · Type a score and press Enter (or ↓/↑) to move down · empty = missing · Esc undoes</div></div>
        <div className="row"><ScopePicker /><button type="button" className="btn primary" disabled={!calendar.data} onClick={() => setAdding(true)}>+ Assignment</button></div>
      </div>
      <ScopeStatus />
      <ErrorBox error={calendar.error} onRetry={() => calendar.refetch()} />
      {calendar.data && <p className="muted">School dates use {calendar.data.timezone}.</p>}
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {q.isLoading && <Loading />}
      {gb && (gb.rows.length === 0 ? (
        <EmptyState title="No students in this section"><p>Add students to start entering grades.</p><div className="row"><Link className="btn primary" to="/roster">Add students</Link></div></EmptyState>
      ) : gb.assessments.length === 0 ? (
        <EmptyState title="No assignments yet"><p>Create your first assignment, then enter scores for {gb.rows.length} students.</p><div className="row"><button type="button" className="btn primary" disabled={!calendar.data} onClick={() => setAdding(true)}>+ New assignment</button></div></EmptyState>
      ) : (
        <div className="card table-wrap gb-wrap" ref={wrap}>
          <table className="gb">
            <caption className="sr-only">Gradebook for {section.name}. Column headers sort the table.</caption>
            <thead>
              <tr>
                <th aria-sort={aria('name')}><button type="button" className="sort-btn" onClick={() => toggleSort('name')}>Student{ind('name')}</button></th>
                <th aria-sort={aria('avg')}><button type="button" className="sort-btn" onClick={() => toggleSort('avg')}>Avg{ind('avg')}</button></th>
                {gb.assessments.map((a) => (
                  <th key={a.id} className="assess" aria-sort={aria(a.id)} title={`${a.kind} · due ${a.due_date}`}>
                    <button type="button" className="sort-btn" onClick={() => toggleSort(a.id)}>{a.title}{ind(a.id)}</button>
                    <div className="sub">/{a.max_points}</div>
                    <button type="button" className="btn small" aria-label={`Edit ${a.title}`} onClick={() => setEditing(a)}>Edit</button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={r.student_id}>
                  <td className="name"><Link to={`/students/${r.student_id}`}>{r.name}</Link></td>
                  <td className="num" style={{ color: gradeColor(r.average), fontWeight: 600 }}>{fmt(r.average, '%')} <span className="muted">{r.letter}</span></td>
                  {gb.assessments.map((a, ci) => (
                    <td key={a.id}>
                      <ScoreCell label={`${r.name}, ${a.title}`} max={a.max_points} value={r.points[a.id] ?? null} cell={`${ri}:${ci}`} onNav={nav}
                        onSave={(points) => save.mutateAsync({ aid: a.id, student_id: r.student_id, points, name: r.name, title: a.title, sectionId: section.id })} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Class average</td>
                <td className="num" style={{ color: gradeColor(mean(gb.rows.map((r) => r.average))) }}>{fmt(mean(gb.rows.map((r) => r.average)), '%')}</td>
                {colAvg.map((v, i) => <td key={gb.assessments[i].id} className="num" style={{ color: gradeColor(v), textAlign: 'right' }}>{fmt(v, '%')}</td>)}
              </tr>
            </tfoot>
          </table>
        </div>
      ))}
      {adding && calendar.data && <NewAssessment schoolDay={calendar.data.today} sectionId={section.id} onClose={() => setAdding(false)} />}
      {editing && editing.section_id === section.id && <EditAssessment key={editing.id} assessment={editing} onClose={() => setEditing(null)} />}
    </>
  );
}
