import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, fmt } from '../api';
import { useScope } from '../scope';
import { ScopePicker } from '../App';
import { Bar, ErrorBox, Loading, Modal, RiskChip, gradeColor } from '../components/ui';

const COLS = [
  ['name', 'Student'], ['section', 'Class', 'hide-sm'], ['average', 'Average'], ['trend', 'Trend', 'hide-sm'],
  ['attendance_rate', 'Attendance', 'hide-sm'], ['homework_rate', 'Homework', 'hide-sm'], ['risk', 'Status'],
];
const RISK_ORDER = { at_risk: 0, watch: 1, on_track: 2 };

function Trend({ v }) {
  if (v == null) return <span className="muted">—</span>;
  const up = v >= 3, down = v <= -3;
  return <span className="num" style={{ color: up ? 'var(--good)' : down ? 'var(--bad)' : 'var(--muted)' }}>{up ? '▲' : down ? '▼' : '•'} {Math.abs(v).toFixed(0)}</span>;
}

export function NewStudentDialog({ onClose }) {
  const { courses, allSections } = useScope();
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: '', grade_level: 9, section_id: allSections[0]?.id ?? '' });
  const create = useMutation({
    mutationFn: () => api('/students', { method: 'POST', body: { ...form, grade_level: Number(form.grade_level) } }),
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
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
  const [courseId, setCourseId] = useState('');
  const [name, setName] = useState('');
  const create = useMutation({
    mutationFn: async () => {
      const course = courseId ? { id: courseId } : await api('/courses', { method: 'POST', body: { name } });
      return courseId ? api('/sections', { method: 'POST', body: { course_id: courseId, name } }) : api('/sections', { method: 'POST', body: { course_id: course.id, name: 'Period 1' } });
    },
    onSuccess: () => { qc.invalidateQueries(); onClose(); },
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

export default function Roster() {
  const { course, section } = useScope();
  const nav = useNavigate();
  const [search, setSearch] = useState('');
  const [risk, setRisk] = useState('');
  const [sort, setSort] = useState({ key: 'risk', dir: 1 });
  const [dialog, setDialog] = useState(null);

  const q = useQuery({
    queryKey: ['students', course?.id, section?.id],
    queryFn: () => api(`/students?${new URLSearchParams({ ...(course && { course_id: course.id }), ...(section && { section_id: section.id }) })}`),
  });
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const get = (r) => sort.key === 'risk' ? RISK_ORDER[r.risk] : sort.key === 'section' ? `${r.course} ${r.section}` : r[sort.key];
    return (q.data ?? [])
      .filter((r) => (!risk || r.risk === risk) && (!term || r.name.toLowerCase().includes(term)))
      .sort((a, b) => {
        const [x, y] = [get(a), get(b)];
        if (x == null) return 1; if (y == null) return -1;   // empty values always last
        return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
      });
  }, [q.data, search, risk, sort]);
  const toggleSort = (key) => setSort((s) => ({ key, dir: s.key === key ? -s.dir : 1 }));

  return (
    <>
      <div className="topbar">
        <div><h1>Roster</h1><div className="page-sub">{q.data ? `${rows.length} of ${q.data.length} students` : ' '}</div></div>
        <div className="row"><ScopePicker /><button className="btn" onClick={() => setDialog('class')}>+ Course</button><button className="btn primary" onClick={() => setDialog('student')}>+ Student</button></div>
      </div>
      <div className="row" style={{ marginBottom: 14 }}>
        <input className="input" style={{ maxWidth: 280 }} type="search" placeholder="Search students…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search students" />
        <div className="seg" role="group" aria-label="Filter by status">
          {[['', 'All'], ['at_risk', 'At risk'], ['watch', 'Watch'], ['on_track', 'On track']].map(([v, l]) => <button key={v} className={risk === v ? 'on' : ''} onClick={() => setRisk(v)}>{l}</button>)}
        </div>
      </div>
      <ErrorBox error={q.error} />
      {q.isLoading ? <Loading /> : (
        <div className="card table-wrap" style={{ padding: 6 }}>
          <table>
            <thead><tr>{COLS.map(([k, l, c = '']) => <th key={k} className={`sortable ${c}`} onClick={() => toggleSort(k)} aria-sort={sort.key === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>{l}{sort.key === k && (sort.dir > 0 ? ' ↑' : ' ↓')}</th>)}</tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="link" tabIndex={0} onClick={() => nav(`/students/${r.id}`)} onKeyDown={(e) => e.key === 'Enter' && nav(`/students/${r.id}`)}>
                  <td className="name">{r.name}<div className="muted" style={{ fontWeight: 400, fontSize: '.8rem' }}>Grade {r.grade_level}</div></td>
                  <td className="hide-sm">{r.course}<div className="muted" style={{ fontSize: '.8rem' }}>{r.section}</div></td>
                  <td><span className="num" style={{ color: gradeColor(r.average), fontWeight: 600 }}>{fmt(r.average, '%')}</span> <span className="muted">{r.letter}</span></td>
                  <td className="hide-sm"><Trend v={r.trend} /></td>
                  <td className="hide-sm" style={{ minWidth: 110 }}><span className="num">{fmt(r.attendance_rate, '%')}</span><Bar value={r.attendance_rate} /></td>
                  <td className="hide-sm" style={{ minWidth: 110 }}><span className="num">{fmt(r.homework_rate, '%')}</span><Bar value={r.homework_rate} /></td>
                  <td><RiskChip risk={r.risk} /></td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={COLS.length} className="empty">No students match.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {dialog === 'student' && <NewStudentDialog onClose={() => setDialog(null)} />}
      {dialog === 'class' && <NewClassDialog onClose={() => setDialog(null)} />}
    </>
  );
}
