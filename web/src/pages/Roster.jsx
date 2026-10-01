import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, fmt } from '../api';
import { useScope } from '../scope';
import ScopePicker from '../components/ScopePicker';
import { useToast } from '../components/Toast';
import { Bar, EmptyState, ErrorBox, Loading, Modal, RiskChip, gradeColor } from '../components/ui';

const COLS = [
  ['name', 'Student'], ['section', 'Class', 'hide-sm'], ['average', 'Average'], ['trend', 'Trend', 'hide-sm'],
  ['attendance_rate', 'Attendance', 'hide-sm'], ['homework_rate', 'Homework', 'hide-sm'], ['risk', 'Status'],
];
export const RISK_ORDER = { at_risk: 0, watch: 1, on_track: 2 };
const FILTERS = [['', 'All'], ['at_risk', 'At risk'], ['watch', 'Watch'], ['on_track', 'On track']];

function Trend({ v }) {
  if (v == null) return <span className="muted">—</span>;
  const up = v >= 3, down = v <= -3;
  return <span className="num" style={{ color: up ? 'var(--good)' : down ? 'var(--bad)' : 'var(--muted)' }}>{up ? '▲' : down ? '▼' : '•'} {Math.abs(v).toFixed(0)}</span>;
}

export function NewStudentDialog({ onClose }) {
  const { courses, allSections } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ name: '', grade_level: 9, section_id: allSections[0]?.id ?? '' });
  const create = useMutation({
    mutationFn: () => api('/students', { method: 'POST', body: { ...form, grade_level: Number(form.grade_level) } }),
    onSuccess: () => { qc.invalidateQueries(); toast.success(`Added ${form.name.trim()}`); onClose(); },
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  return (
    <Modal title="Add student" onClose={onClose}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="field">Name<input className="input" autoFocus required value={form.name} onChange={set('name')} /></label>
        <label className="field">Grade level
          <select className="input" value={form.grade_level} onChange={set('grade_level')}>{[...Array(12)].map((_, i) => <option key={i + 1}>{i + 1}</option>)}</select>
        </label>
        <label className="field">Section
          <select className="input" required value={form.section_id} onChange={set('section_id')}>
            {courses.map((c) => <optgroup key={c.id} label={c.name}>{c.sections.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</optgroup>)}
          </select>
        </label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={create.isPending || !form.section_id}>Add student</button>
        </div>
      </form>
    </Modal>
  );
}

export function NewClassDialog({ onClose }) {
  const { courses } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const [courseId, setCourseId] = useState('');
  const [name, setName] = useState('');
  const create = useMutation({
    mutationFn: async () => {
      const course = courseId ? { id: courseId } : await api('/courses', { method: 'POST', body: { name } });
      return courseId ? api('/sections', { method: 'POST', body: { course_id: courseId, name } }) : api('/sections', { method: 'POST', body: { course_id: course.id, name: 'Period 1' } });
    },
    onSuccess: () => { qc.invalidateQueries(); toast.success(courseId ? `Added section ${name.trim()}` : `Added ${name.trim()}`); onClose(); },
  });
  return (
    <Modal title="Add course or section" onClose={onClose}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="field">Add to
          <select className="input" value={courseId} onChange={(e) => setCourseId(e.target.value)}>
            <option value="">New course…</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.name} (new section)</option>)}
          </select>
        </label>
        <label className="field">{courseId ? 'Section name' : 'Course name'}
          <input className="input" required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={courseId ? 'Period 6' : 'Chemistry'} />
        </label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={create.isPending}>Create</button>
        </div>
      </form>
    </Modal>
  );
}

function ImportDialog({ onClose }) {
  const { allSections } = useScope();
  const qc = useQueryClient();
  const [sectionId, setSectionId] = useState(allSections[0]?.id ?? '');
  const [text, setText] = useState('');
  const run = useMutation({
    mutationFn: () => api(`/sections/${sectionId}/import`, { method: 'POST', body: { csv: text } }),
    onSuccess: () => qc.invalidateQueries(),
  });
  const onFile = async (e) => { const f = e.target.files[0]; if (f) setText(await f.text()); };
  return (
    <Modal title="Import students from CSV" onClose={onClose}>
      <div className="grid">
        <label className="field">Section
          <select className="input" value={sectionId} onChange={(e) => setSectionId(e.target.value)}>
            {allSections.map((s) => <option key={s.id} value={s.id}>{s.course} · {s.name}</option>)}
          </select>
        </label>
        <label className="field">CSV file (columns: name, grade_level)<input className="input" type="file" accept=".csv,text/csv" onChange={onFile} /></label>
        <textarea className="input" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={'name,grade_level\nAda Lovelace,10'} aria-label="CSV text" />
        <ErrorBox error={run.error} />
        {run.data && <div role="status"><strong>{run.data.created} added.</strong>{run.data.skipped.length > 0 && <ul>{run.data.skipped.map((m) => <li key={m} className="muted">{m}</li>)}</ul>}</div>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" onClick={onClose}>{run.data ? 'Done' : 'Cancel'}</button>
          <button type="button" className="btn primary" disabled={run.isPending || !text.trim() || !sectionId} onClick={() => run.mutate()}>Import</button>
        </div>
      </div>
    </Modal>
  );
}

const VALID_SORT = new Set(COLS.map(([k]) => k));

export default function Roster() {
  const { course, section } = useScope();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState(null);

  // Filters live in the URL so a refresh, back button or shared link keeps the view.
  const search = params.get('q') ?? '';
  const risk = FILTERS.some(([v]) => v === params.get('status')) ? params.get('status') ?? '' : '';
  const sort = { key: VALID_SORT.has(params.get('sort')) ? params.get('sort') : 'risk', dir: params.get('dir') === 'desc' ? -1 : 1 };
  const update = (patch) => setParams((p) => {
    const n = new URLSearchParams(p);
    Object.entries(patch).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
    return n;
  }, { replace: true });

  const q = useQuery({
    queryKey: ['students', course?.id, section?.id],
    queryFn: () => api(`/students?${new URLSearchParams({ ...(course && { course_id: course.id }), ...(section && { section_id: section.id }) })}`),
  });
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const get = (r) => sort.key === 'risk' ? RISK_ORDER[r.risk] : sort.key === 'section' ? `${r.course} ${r.section}` : sort.key === 'name' ? r.name.toLowerCase() : r[sort.key];
    return (q.data ?? [])
      .filter((r) => (!risk || r.risk === risk) && (!term || r.name.toLowerCase().includes(term)))
      .sort((a, b) => {
        const [x, y] = [get(a), get(b)];
        if (x == null && y == null) return 0;
        if (x == null) return 1; if (y == null) return -1;   // empty values always last
        return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
      });
  }, [q.data, search, risk, sort.key, sort.dir]);
  const toggleSort = (key) => {
    const dir = sort.key === key ? -sort.dir : 1;
    update({ sort: key === 'risk' && dir === 1 ? '' : key, dir: dir === -1 ? 'desc' : '' });
  };
  const clear = () => setParams({}, { replace: true });
  const filtered = search || risk;

  return (
    <>
      <div className="topbar">
        <div><h1>Roster</h1><div className="page-sub" aria-live="polite">{q.data ? `${rows.length} of ${q.data.length} students` : ' '}</div></div>
        <div className="row"><ScopePicker /><button type="button" className="btn" onClick={() => setDialog('import')}>Import CSV</button><button type="button" className="btn" onClick={() => setDialog('class')}>+ Course</button><button type="button" className="btn primary" onClick={() => setDialog('student')}>+ Student</button></div>
      </div>
      <div className="row" style={{ marginBottom: 14 }}>
        <input className="input" style={{ maxWidth: 280 }} type="search" placeholder="Search students…" value={search} onChange={(e) => update({ q: e.target.value })} aria-label="Search students" />
        <div className="seg" role="group" aria-label="Filter by status">
          {FILTERS.map(([v, l]) => <button type="button" key={v} className={risk === v ? 'on' : ''} aria-pressed={risk === v} onClick={() => update({ status: v })}>{l}</button>)}
        </div>
        {filtered && <button type="button" className="btn small" onClick={clear}>Clear filters</button>}
      </div>
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {q.isLoading ? <Loading /> : q.data && q.data.length === 0 ? (
        <EmptyState title="No students yet">
          <p>Add your first student, or import a whole class from a CSV.</p>
          <div className="row"><button type="button" className="btn primary" onClick={() => setDialog('student')}>+ Add student</button><button type="button" className="btn" onClick={() => setDialog('import')}>Import CSV</button></div>
        </EmptyState>
      ) : q.data && (
        <div className="card table-wrap" style={{ padding: 6 }}>
          <table>
            <caption className="sr-only">Students. Column headers sort the table.</caption>
            <thead><tr>{COLS.map(([k, l, c = '']) => (
              <th key={k} className={c} aria-sort={sort.key === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                <button type="button" className="sort-btn" onClick={() => toggleSort(k)}>{l}{sort.key === k && (sort.dir > 0 ? ' ↑' : ' ↓')}</button>
              </th>
            ))}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="link" onClick={(e) => { if (!e.target.closest('a')) nav(`/students/${r.id}`); }}>
                  <td className="name"><Link className="row-link" to={`/students/${r.id}`}>{r.name}</Link><div className="muted" style={{ fontWeight: 400, fontSize: '.8rem' }}>Grade {r.grade_level}</div></td>
                  <td className="hide-sm">{r.course}<div className="muted" style={{ fontSize: '.8rem' }}>{r.section}</div></td>
                  <td><span className="num" style={{ color: gradeColor(r.average), fontWeight: 600 }}>{fmt(r.average, '%')}</span> <span className="muted">{r.letter}</span></td>
                  <td className="hide-sm"><Trend v={r.trend} /></td>
                  <td className="hide-sm" style={{ minWidth: 110 }}><span className="num">{fmt(r.attendance_rate, '%')}</span><Bar value={r.attendance_rate} /></td>
                  <td className="hide-sm" style={{ minWidth: 110 }}><span className="num">{fmt(r.homework_rate, '%')}</span><Bar value={r.homework_rate} /></td>
                  <td><RiskChip risk={r.risk} /></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={COLS.length} className="empty">No students match. {filtered && <button type="button" className="btn small" onClick={clear}>Clear filters</button>}</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {dialog === 'student' && <NewStudentDialog onClose={() => setDialog(null)} />}
      {dialog === 'import' && <ImportDialog onClose={() => setDialog(null)} />}
      {dialog === 'class' && <NewClassDialog onClose={() => setDialog(null)} />}
    </>
  );
}
