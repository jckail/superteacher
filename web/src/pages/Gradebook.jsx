import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api';
import { useActiveSection, useScope } from '../scope';
import ScopePicker from '../components/ScopePicker';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorBox, Loading, Modal, gradeColor } from '../components/ui';

const today = () => new Date().toISOString().slice(0, 10);

function NewAssessment({ sectionId, onClose }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState({ title: '', kind: 'homework', max_points: 10, due_date: today() });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const create = useMutation({
    mutationFn: () => api(`/sections/${sectionId}/assessments`, { method: 'POST', body: { ...f, title: f.title.trim(), max_points: Number(f.max_points) } }),
    onSuccess: (gb) => { qc.setQueryData(['gradebook', sectionId], gb); qc.invalidateQueries(); toast.success(`Added “${f.title.trim()}”`); onClose(); },
  });
  return (
    <Modal title="New assignment" onClose={onClose}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="field">Title<input className="input" required autoFocus value={f.title} onChange={set('title')} /></label>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>Type<select className="input" value={f.kind} onChange={set('kind')}>{['homework', 'quiz', 'test', 'project'].map((k) => <option key={k}>{k}</option>)}</select></label>
          <label className="field" style={{ width: 110 }}>Max points<input className="input" type="number" required min="1" step="any" value={f.max_points} onChange={set('max_points')} /></label>
        </div>
        <label className="field">Due<input className="input" type="date" value={f.due_date} onChange={set('due_date')} /></label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={create.isPending || !f.title.trim()}>Create</button></div>
      </form>
    </Modal>
  );
}

/**
 * Edit-in-place score. Commits once on blur/Enter when the value changed and is valid;
 * Escape or a failed save puts the previous value back. Over-max scores are allowed (extra credit) but flagged.
 * `onSave(points)` may return a promise; if it rejects the draft reverts.
 */
export function ScoreCell({ value, max, onSave, label, onNav, cell }) {
  const [draft, setDraft] = useState(value ?? '');
  const [prev, setPrev] = useState(value);
  if (prev !== value) { setPrev(value); setDraft(value ?? ''); }   // server/optimistic value changed → resync

  const text = String(draft).trim();
  const num = text === '' ? null : Number(text);
  const invalid = text !== '' && (Number.isNaN(num) || num < 0);
  const over = !invalid && num != null && max != null && num > max;

  const commit = () => {
    if (invalid) { setDraft(value ?? ''); return; }
    if (num === value) { setDraft(value ?? ''); return; }
    Promise.resolve(onSave(num)).catch(() => setDraft(value ?? ''));
  };
  const onKeyDown = (e) => {
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
        value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit} onKeyDown={onKeyDown} />
      {(over || invalid) && <span className="cell-warn" role="status">{invalid ? 'Enter a number ≥ 0' : `Over ${max}`}</span>}
    </>
  );
}

const mean = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

export default function Gradebook() {
  const section = useActiveSection();
  const { isLoading: scopeLoading } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [sort, setSort] = useState({ key: 'name', dir: 1 });
  const wrap = useRef(null);
  const key = ['gradebook', section?.id];
  const q = useQuery({ queryKey: key, queryFn: () => api(`/sections/${section.id}/gradebook`), enabled: !!section });

  const save = useMutation({
    mutationKey: ['gb-score'],
    mutationFn: ({ aid, student_id, points }) => api(`/assessments/${aid}/scores`, { method: 'PUT', body: { scores: [{ student_id, points }] } }),
    onMutate: async ({ aid, student_id, points }) => {   // optimistic: show the new score immediately
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData(key);
      qc.setQueryData(key, (d) => d && ({ ...d, rows: d.rows.map((r) => (r.student_id === student_id ? { ...r, points: { ...r.points, [aid]: points } } : r)) }));
      return { prev };
    },
    onError: (e, v, ctx) => {
      ctx?.prev && qc.setQueryData(key, (d) => d && ({ ...d, rows: d.rows.map((r) => (r.student_id === v.student_id ? { ...r, points: { ...r.points, [v.aid]: ctx.prev.rows.find((x) => x.student_id === v.student_id)?.points[v.aid] ?? null } } : r)) }));
      toast.error(`Couldn’t save ${v.name}’s score for ${v.title}: ${e.message}`);
    },
    onSuccess: (gb, v) => {
      if (qc.isMutating({ mutationKey: ['gb-score'] }) <= 1) qc.setQueryData(key, gb);   // don't clobber newer in-flight edits
      qc.invalidateQueries({ queryKey: ['overview'] }); qc.invalidateQueries({ queryKey: ['students'] }); qc.invalidateQueries({ queryKey: ['student'] });
      toast.success(`Saved ${v.name} · ${v.title}`);
    },
  });

  const gb = q.data;
  const rows = useMemo(() => {
    if (!gb) return [];
    const get = (r) => (sort.key === 'name' ? r.name.toLowerCase() : sort.key === 'avg' ? r.average : (r.points[sort.key] ?? null));
    return [...gb.rows].sort((a, b) => {
      const [x, y] = [get(a), get(b)];
      if (x == null && y == null) return 0;
      if (x == null) return 1; if (y == null) return -1;   // empty values always last
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
    });
  }, [gb, sort]);
  const colAvg = useMemo(() => (gb ? gb.assessments.map((a) => mean(gb.rows.map((r) => (r.points[a.id] == null ? null : (r.points[a.id] / a.max_points) * 100)))) : []), [gb]);
  const toggleSort = (k) => setSort((s) => ({ key: k, dir: s.key === k ? -s.dir : (k === 'name' ? 1 : -1) }));

  /** Move focus to the cell above/below in the same column. Returns false at the edge. */
  const nav = (dir, cell) => {
    const [r, c] = cell.split(':').map(Number);
    const next = wrap.current?.querySelector(`[data-cell="${r + (dir === 'down' ? 1 : -1)}:${c}"]`);
    if (!next) return false;
    next.focus(); next.select?.();
    return true;
  };

  if (scopeLoading) return <Loading />;
  if (!section) return (
    <>
      <div className="topbar"><h1>Gradebook</h1></div>
      <EmptyState title="No classes yet"><p>Create a course and section to start grading.</p><div className="row"><Link className="btn primary" to="/roster">Go to roster</Link></div></EmptyState>
    </>
  );
  const ind = (k) => (sort.key === k ? (sort.dir > 0 ? ' ↑' : ' ↓') : '');
  const aria = (k) => (sort.key === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none');
  return (
    <>
      <div className="topbar">
        <div><h1>Gradebook</h1><div className="page-sub">{section.name} · Type a score and press Enter (or ↓/↑) to move down · empty = missing · Esc undoes</div></div>
        <div className="row"><ScopePicker /><button type="button" className="btn primary" onClick={() => setAdding(true)}>+ Assignment</button></div>
      </div>
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {q.isLoading && <Loading />}
      {gb && (gb.rows.length === 0 ? (
        <EmptyState title="No students in this section"><p>Add students to start entering grades.</p><div className="row"><Link className="btn primary" to="/roster">Add students</Link></div></EmptyState>
      ) : gb.assessments.length === 0 ? (
        <EmptyState title="No assignments yet"><p>Create your first assignment, then enter scores for {gb.rows.length} students.</p><div className="row"><button type="button" className="btn primary" onClick={() => setAdding(true)}>+ New assignment</button></div></EmptyState>
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
                        onSave={(points) => save.mutateAsync({ aid: a.id, student_id: r.student_id, points, name: r.name, title: a.title })} />
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
      {adding && <NewAssessment sectionId={section.id} onClose={() => setAdding(false)} />}
    </>
  );
}
