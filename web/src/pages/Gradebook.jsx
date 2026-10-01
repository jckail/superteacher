import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api';
import { useActiveSection, useScope } from '../scope';
import { ScopePicker } from '../App';
import { ErrorBox, Loading, Modal, gradeColor } from '../components/ui';

function NewAssessment({ sectionId, onClose }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ title: '', kind: 'homework', max_points: 10, due_date: new Date().toISOString().slice(0, 10) });
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const create = useMutation({
    mutationFn: () => api(`/sections/${sectionId}/assessments`, { method: 'POST', body: { ...f, max_points: Number(f.max_points) } }),
    onSuccess: (gb) => { qc.setQueryData(['gradebook', sectionId], gb); qc.invalidateQueries(); onClose(); },
  });
  return (
    <Modal title="New assignment" onClose={onClose}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="field">Title<input className="input" required autoFocus value={f.title} onChange={set('title')} /></label>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>Type<select className="input" value={f.kind} onChange={set('kind')}>{['homework', 'quiz', 'test', 'project'].map((k) => <option key={k}>{k}</option>)}</select></label>
          <label className="field" style={{ width: 110 }}>Max points<input className="input" type="number" min="1" step="any" value={f.max_points} onChange={set('max_points')} /></label>
        </div>
        <label className="field">Due<input className="input" type="date" value={f.due_date} onChange={set('due_date')} /></label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={create.isPending}>Create</button></div>
      </form>
    </Modal>
  );
}

/** Uncontrolled-until-blur cell: saves once when the teacher leaves the field, only if it changed. */
function ScoreCell({ value, max, onSave, label }) {
  const [draft, setDraft] = useState(value ?? '');
  const [prev, setPrev] = useState(value);
  if (prev !== value) { setPrev(value); setDraft(value ?? ''); }   // server value changed → resync
  const commit = () => {
    const next = draft === '' ? null : Number(draft);
    if (next !== value && !(next != null && Number.isNaN(next))) onSave(next);
  };
  return (
    <input className={`grade-input num ${value == null ? 'missing' : ''}`} inputMode="decimal" aria-label={label} title={`out of ${max}`}
      value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
  );
}

export default function Gradebook() {
  const section = useActiveSection();
  const { isLoading: scopeLoading } = useScope();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ['gradebook', section?.id], queryFn: () => api(`/sections/${section.id}/gradebook`), enabled: !!section });
  const save = useMutation({
    mutationFn: ({ aid, student_id, points }) => api(`/assessments/${aid}/scores`, { method: 'PUT', body: { scores: [{ student_id, points }] } }),
    onSuccess: (gb) => { qc.setQueryData(['gradebook', section.id], gb); qc.invalidateQueries({ queryKey: ['overview'] }); qc.invalidateQueries({ queryKey: ['students'] }); },
  });
  if (scopeLoading) return <Loading />;
  if (!section) return <div className="card empty">Create a course and section on the roster first.</div>;
  const gb = q.data;
  return (
    <>
      <div className="topbar">
        <div><h1>Gradebook</h1><div className="page-sub">Click a score to edit · Enter to save · empty = missing</div></div>
        <div className="row"><ScopePicker /><button className="btn primary" onClick={() => setAdding(true)}>+ Assignment</button></div>
      </div>
      <p className="muted" style={{ marginTop: -8 }}>Showing <strong>{section.name}</strong></p>
      <ErrorBox error={q.error || save.error} />
      {q.isLoading && <Loading />}
      {gb && (gb.rows.length === 0 ? <div className="card empty">No students in this section.</div> : (
        <div className="card table-wrap" style={{ padding: 6 }}>
          <table>
            <thead><tr><th>Student</th><th>Avg</th>{gb.assessments.map((a) => <th key={a.id} title={`${a.kind} · ${a.due_date}`}>{a.title}<div style={{ fontWeight: 400, textTransform: 'none' }}>/{a.max_points}</div></th>)}</tr></thead>
            <tbody>
              {gb.rows.map((r) => (
                <tr key={r.student_id}>
                  <td className="name"><Link to={`/students/${r.student_id}`}>{r.name}</Link></td>
                  <td className="num" style={{ color: gradeColor(r.average), fontWeight: 600 }}>{fmt(r.average, '%')} <span className="muted">{r.letter}</span></td>
                  {gb.assessments.map((a) => (
                    <td key={a.id}><ScoreCell label={`${r.name} ${a.title}`} max={a.max_points} value={r.points[a.id] ?? null}
                      onSave={(points) => save.mutate({ aid: a.id, student_id: r.student_id, points })} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {adding && <NewAssessment sectionId={section.id} onClose={() => setAdding(false)} />}
    </>
  );
}
