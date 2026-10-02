import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import type { AssessmentKind, CourseOut, GradeHistoryOut, GradeHistorySection, Insight as InsightData, NoteOut, StudentDetail, StudentPatch } from '../types';
import { ApiError, api, fmt } from '../api';
import { useConfirm } from '../components/Confirm';
import { useToast } from '../components/Toast';
import { AttendanceHeat, TrendChart } from '../components/charts';
import { EmptyState, ErrorBox, Loading, Modal, RiskChip, Stat, gradeColor } from '../components/ui';

function Insight({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['insight', id], queryFn: ({ signal }) => api<InsightData>(`/students/${id}/insight`, { signal }), staleTime: 5 * 60_000 });
  const i = q.data;
  return (
    <section className="card insight">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2>✨ Insight</h2>
        {i && <span className="chip neutral">{i.source === 'ai' ? 'AI' : 'Rule-based'}</span>}
      </div>
      {q.isLoading && <Loading />}
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {i && (
        <>
          <strong>{i.headline}</strong>
          {([['Strengths', i.strengths], ['Concerns', i.concerns], ['Suggested actions', i.actions]] satisfies [string, string[]][]).map(([t, items]) => items.length > 0 && (
            <div key={t}><h3>{t}</h3><ul>{items.map((x) => <li key={x}>{x}</li>)}</ul></div>
          ))}
          {i.source === 'rules' && <p className="muted" style={{ fontSize: '.85rem' }}>This summary uses recorded grades and attendance. AI-written suggestions are unavailable.</p>}
        </>
      )}
    </section>
  );
}

export function Notes({ student }: { student: StudentDetail }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [body, setBody] = useState('');
  const confirm = useConfirm();
  const [editing, setEditing] = useState<NoteOut | null>(null);
  const [draft, setDraft] = useState('');
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['student', student.id] });
    void qc.invalidateQueries({ queryKey: ['insight', student.id] });
  };
  const edit = useMutation({
    mutationFn: ({ noteId, text }: { noteId: string; text: string }) => api<NoteOut>(`/students/${student.id}/notes/${noteId}`, { method: 'PATCH', body: { body: text } }),
    onSuccess: () => { setEditing(null); toast.success('Note updated'); refresh(); },
  });
  const remove = useMutation({
    mutationFn: (noteId: string) => api<null>(`/students/${student.id}/notes/${noteId}`, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Note deleted'); refresh(); },
    onError: (error) => toast.error(`Couldn’t delete note: ${error.message}`),
  });
  const deleteNote = async (note: NoteOut) => {
    if (await confirm({ title: 'Delete private note?', message: note.body, confirmLabel: 'Delete note', danger: true })) remove.mutate(note.id);
  };
  const closeEdit = () => { if (!edit.isPending) setEditing(null); };
  const add = useMutation({
    mutationFn: () => api<NoteOut>(`/students/${student.id}/notes`, { method: 'POST', body: { body: body.trim() } }),
    onSuccess: () => { setBody(''); toast.success('Note added'); refresh(); },
  });
  return (
    <section className="card">
      <h2>Notes</h2>
      <form className="row" onSubmit={(e) => { e.preventDefault(); if (body.trim()) add.mutate(); }}>
        <input className="input" style={{ flex: 1 }} value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} placeholder="Add a private note…" aria-label="New note" />
        <button className="btn" disabled={add.isPending || !body.trim()}>Add</button>
      </form>
      <ErrorBox error={add.error} />
      {student.notes.map((n) => (
        <div className="note" key={n.id}>
          <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{n.body}</p>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span className="muted" style={{ fontSize: '.8rem' }}>{new Date(n.created_at).toLocaleDateString()}</span>
            <div className="row">
              <button type="button" className="btn small" aria-label={`Edit note: ${n.body}`} disabled={remove.isPending} onClick={() => { edit.reset(); setEditing(n); setDraft(n.body); }}>Edit</button>
              <button type="button" className="btn small danger" aria-label={`Delete note: ${n.body}`} disabled={remove.isPending} onClick={() => void deleteNote(n)}>Delete</button>
            </div>
          </div>
        </div>
      ))}
      {editing && <Modal title="Edit private note" onClose={closeEdit}>
        <form className="grid" onSubmit={(event) => { event.preventDefault(); if (draft.trim() && !edit.isPending) edit.mutate({ noteId: editing.id, text: draft.trim() }); }}>
          <label className="field">Note<textarea className="input" required autoFocus maxLength={2000} rows={5} value={draft} disabled={edit.isPending} onChange={(event) => setDraft(event.target.value)} /></label>
          <ErrorBox error={edit.error} />
          <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" disabled={edit.isPending} onClick={closeEdit}>Cancel</button><button className="btn primary" disabled={edit.isPending || !draft.trim() || draft.trim() === editing.body}>Save note</button></div>
        </form>
      </Modal>}
    </section>
  );
}

export function StudentProfile({ student }: { student: StudentDetail }) {
  const [editing, setEditing] = useState(false);
  return <>
    <button type="button" className="btn" onClick={() => setEditing(true)}>Edit student</button>
    {editing && <EditStudent key={student.id} student={student} onClose={() => setEditing(false)} />}
  </>;
}

export function EditStudent({ student, onClose }: { student: StudentDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(student.name);
  const [grade, setGrade] = useState(String(student.grade_level));
  const [section, setSection] = useState(student.section_id);
  const courses = useQuery({ queryKey: ['courses'], queryFn: ({ signal }) => api<CourseOut[]>('/courses', { signal }) });
  const sections = courses.data?.flatMap((course) => course.sections.map((item) => ({ ...item, course: course.name }))) ?? [];
  const gradeNumber = Number(grade);
  const valid = Boolean(name.trim() && Number.isInteger(gradeNumber) && gradeNumber >= 1 && gradeNumber <= 12 && section);
  const moved = section !== student.section_id;
  const changed = name.trim() !== student.name || gradeNumber !== student.grade_level || moved;
  const save = useMutation({
    mutationFn: ({ id, body }: { id: string; body: StudentPatch }) => api<StudentDetail>(`/students/${id}`, { method: 'PATCH', body }),
    onSuccess: (updated, variables) => {
      qc.setQueryData(['student', variables.id], updated);
      for (const key of ['student', 'students', 'overview', 'gradebook', 'report-summary', 'insight', 'grade-history']) void qc.invalidateQueries({ queryKey: [key] });
      toast.success('Student updated'); onClose();
    },
  });
  const close = () => { if (!save.isPending) onClose(); };
  return <Modal title="Edit student" onClose={close}>
    <form className="grid" onSubmit={(event) => {
      event.preventDefault();
      if (valid && changed && !save.isPending) save.mutate({ id: student.id, body: { name: name.trim(), grade_level: gradeNumber, section_id: section } });
    }}>
      <label className="field">Name<input className="input" autoFocus required maxLength={120} disabled={save.isPending} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label className="field">Grade level<input className="input" type="number" required min="1" max="12" step="1" disabled={save.isPending} value={grade} onChange={(event) => setGrade(event.target.value)} /></label>
      <label className="field">Section<select className="input" required disabled={save.isPending || courses.isLoading} value={section} onChange={(event) => setSection(event.target.value)}>
        {!sections.some((item) => item.id === student.section_id) && <option value={student.section_id}>{student.course} · {student.section}</option>}
        {sections.map((item) => <option key={item.id} value={item.id}>{item.course} · {item.name}</option>)}
      </select></label>
      <ErrorBox error={courses.error} onRetry={() => courses.refetch()} />
      {moved && <p role="status">Changing sections preserves grade history. Current averages will use assignments from the new section; prior grades remain available below.</p>}
      <ErrorBox error={save.error} />
      <div className="row" style={{ justifyContent: 'flex-end' }}><button type="button" className="btn" disabled={save.isPending} onClick={close}>Cancel</button><button className="btn primary" disabled={save.isPending || !valid || !changed}>Save student</button></div>
    </form>
  </Modal>;
}

function HistorySection({ section }: { section: GradeHistorySection }) {
  const [page, setPage] = useState(0);
  const pageSize = 50;
  const pages = Math.max(1, Math.ceil(section.scores.length / pageSize));
  const current = Math.min(page, pages - 1);
  return <section aria-label={`${section.course} · ${section.section}`}>
    <h3>{section.course} · {section.section}</h3>
    <div className="table-wrap"><table>
      <caption className="sr-only">Grades from {section.course} · {section.section}</caption>
      <thead><tr><th>Due</th><th>Assignment</th><th>Type</th><th>Recorded score</th></tr></thead>
      <tbody>{section.scores.slice(current * pageSize, (current + 1) * pageSize).map((score) => <tr key={score.assessment_id}>
        <td className="num">{score.due_date}</td><td>{score.title}</td><td>{score.kind}</td>
        <td className="num">{score.points == null ? 'Not recorded' : `${score.points}/${score.max_points} (${fmt(score.pct, '%')})`}</td>
      </tr>)}</tbody>
    </table></div>
    {pages > 1 && <nav className="row" aria-label={`Grade history pages for ${section.course} · ${section.section}`}>
      <button type="button" className="btn" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous page</button>
      <span aria-live="polite">Page {current + 1} of {pages}</span>
      <button type="button" className="btn" disabled={current === pages - 1} onClick={() => setPage(current + 1)}>Next page</button>
    </nav>}
  </section>;
}

export function GradeHistory({ studentId, activeSectionId }: { studentId: string; activeSectionId: string }) {
  const q = useQuery({ queryKey: ['grade-history', studentId, activeSectionId], queryFn: ({ signal }) => api<GradeHistoryOut>(`/students/${studentId}/grade-history`, { signal }) });
  const data = q.data;
  // A stale response from before a transfer must not mix sections with the current profile.
  const current = data?.student_id === studentId && data.active_section_id === activeSectionId;
  return <section className="card" aria-label="Grade history">
    <h2>Grade history</h2>
    <p className="muted">Previous-section scores are preserved here and do not affect the current-section average. Attendance and private notes stay with the student.</p>
    {q.isLoading && <Loading />}
    <ErrorBox error={q.error} onRetry={() => q.refetch()} />
    {current && (data.sections.length ? data.sections.filter((section) => section.section_id !== activeSectionId).map((section) => <HistorySection key={`${studentId}:${section.section_id}`} section={section} />) : <p className="muted">No grades from previous sections.</p>)}
    {data && !current && <p role="status">The student’s section changed. <button type="button" className="btn small" onClick={() => q.refetch()}>Refresh grade history</button></p>}
  </section>;
}

const short = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

export default function Student() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [kind, setKind] = useState<AssessmentKind | ''>('');
  const q = useQuery({ queryKey: ['student', id], queryFn: ({ signal }) => {
    if (!id) throw new ApiError(404, 'Student not found');
    return api<StudentDetail>(`/students/${id}`, { signal });
  }, retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 1 });
  const del = useMutation({
    mutationFn: () => api<null>(`/students/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries(); toast.success('Student removed'); nav('/roster'); },
    onError: (e) => toast.error(`Couldn’t remove student: ${e.message}`),
  });
  const s = q.data;
  const kinds = useMemo(() => [...new Set((s?.scores ?? []).map((x) => x.kind))], [s]);
  if (q.isLoading) return <Loading />;
  if ((q.error instanceof ApiError && q.error.status === 404) || (q.error && !s && /not found/i.test(q.error.message))) {
    return (
      <>
        <Link className="back" to="/roster">← Roster</Link>
        <EmptyState title="Student not found"><p>This student may have been removed.</p><div className="row"><Link className="btn primary" to="/roster">Back to roster</Link></div></EmptyState>
      </>
    );
  }
  if (q.error) return <><Link className="back" to="/roster">← Roster</Link><ErrorBox error={q.error} onRetry={() => q.refetch()} /></>;

  if (!s) return <Loading />;

  const graded = s.scores.filter((x) => x.pct != null && x.due_date <= s.as_of);
  const lastDays = s.attendance.filter((x) => x.day <= s.as_of).slice(-30);
  const shown = s.scores.filter((x) => !kind || x.kind === kind);
  const remove = async () => {
    if (await confirm({ title: `Remove ${s.name}?`, message: 'This permanently deletes the student and all of their scores, attendance and notes.', confirmLabel: 'Remove student', danger: true })) del.mutate();
  };
  return (
    <>
      <Link className="back" to="/roster">← Roster</Link>
      <div className="topbar" style={{ marginTop: 8 }}>
        <div>
          <h1>{s.name} <RiskChip risk={s.risk} /></h1>
          <div className="page-sub">Grade {s.grade_level} · {s.course} · {s.section}</div>
        </div>
        <div className="row"><StudentProfile key={s.id} student={s} /><button type="button" className="btn danger" onClick={remove} disabled={del.isPending}>Remove student</button></div>
      </div>
      {s.risk_reasons.length > 0 && <p className="muted">⚑ {s.risk_reasons.join(' · ')}</p>}
      <div className="grid stats">
        <Stat label="Average" value={<span style={{ color: gradeColor(s.average) }}>{fmt(s.average, '%')}</span>} hint={s.letter && `${s.letter} · GPA ${s.gpa?.toFixed(1)}`} />
        <Stat label="Attendance" value={fmt(s.attendance_rate, '%')} hint={`${s.absences} absences · ${s.tardies} tardies`} />
        <Stat label="Homework" value={fmt(s.homework_rate, '%')} hint={s.missing ? `${s.missing} missing` : 'Nothing missing'} />
      </div>
      <div className="grid two">
        <div className="grid">
          <section className="card">
            <h2>Score trend</h2>
            <TrendChart points={graded.map((x) => ({ pct: x.pct, label: x.title, short: short(x.due_date), detail: `${x.points}/${x.max_points} · ${x.kind}` }))} />
          </section>
          <Insight id={s.id} />
          <section className="card">
            <h2>Last {lastDays.length} school days</h2>
            <AttendanceHeat days={lastDays} />
          </section>
          <Notes key={s.id} student={s} />
        </div>
        <section className="card table-wrap">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <h2>Assignments</h2>
            {kinds.length > 1 && (
              <div className="seg" role="group" aria-label="Filter by type">
                {([['', 'All'], ...kinds.map((k): [AssessmentKind, string] => [k, k])] satisfies [AssessmentKind | '', string][]).map(([v, l]) => <button type="button" key={v} className={kind === v ? 'on' : ''} aria-pressed={kind === v} onClick={() => setKind(v)}>{l}</button>)}
              </div>
            )}
          </div>
          {s.scores.length === 0 ? <p className="muted">No assignments yet. Add one from the <Link to="/gradebook">gradebook</Link>.</p> : (
            <table>
              <thead><tr><th>Due</th><th>Title</th><th>Score</th></tr></thead>
              <tbody>
                {[...shown].reverse().map((x) => (
                  <tr key={x.assessment_id}>
                    <td className="muted num">{x.due_date.slice(5)}</td>
                    <td>{x.title} <span className="chip neutral">{x.kind}</span></td>
                    <td className="num">{x.points == null ? <span className={`chip ${x.due_date > s.as_of ? 'neutral' : 'bad'}`}>{x.due_date > s.as_of ? 'not yet due' : 'missing'}</span> : <><strong style={{ color: gradeColor(x.pct) }}>{fmt(x.pct, '%')}</strong> <span className="muted">{x.points}/{x.max_points}</span></>}</td>
                  </tr>
                ))}
                {shown.length === 0 && <tr><td colSpan={3} className="empty">Nothing of this type.</td></tr>}
              </tbody>
            </table>
          )}
        </section>
      </div>
      <GradeHistory key={`${s.id}:${s.section_id}`} studentId={s.id} activeSectionId={s.section_id} />
    </>
  );
}
