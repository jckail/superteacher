import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import type { CourseOut, ImportResult, Risk, SectionOut, StudentDetail, StudentSummary } from '../types';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, fmt } from '../api';
import { useScope } from '../scope';
import ScopePicker from '../components/ScopePicker';
import { useToast } from '../components/Toast';
import { Bar, EmptyState, ErrorBox, Loading, Modal, RiskChip, gradeColor } from '../components/ui';

type SortKey = 'name' | 'section' | 'average' | 'trend' | 'attendance_rate' | 'homework_rate' | 'risk';
type DialogProps = { onClose: () => void };
const COLS: readonly (readonly [SortKey, string, string?])[] = [
  ['name', 'Student'], ['section', 'Class', 'hide-sm'], ['average', 'Average'], ['trend', 'Trend', 'hide-sm'],
  ['attendance_rate', 'Attendance', 'hide-sm'], ['homework_rate', 'Homework', 'hide-sm'], ['risk', 'Status'],
];
export const RISK_ORDER: Record<Risk, number> = { at_risk: 0, watch: 1, on_track: 2 };
const FILTERS: readonly (readonly [Risk | '', string])[] = [['', 'All'], ['at_risk', 'At risk'], ['watch', 'Watch'], ['on_track', 'On track']];

function Trend({ v }: { v: number | null }) {
  if (v == null) return <span className="muted">—</span>;
  const up = v >= 3, down = v <= -3;
  return <span className="num" style={{ color: up ? 'var(--good)' : down ? 'var(--bad)' : 'var(--muted)' }}>{up ? '▲' : down ? '▼' : '•'} {Math.abs(v).toFixed(0)}</span>;
}

export function NewStudentDialog({ onClose }: DialogProps) {
  const { courses, allSections } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const busy = useRef(false);
  const [form, setForm] = useState({ name: '', grade_level: '9', section_id: allSections[0]?.id ?? '' });
  const sectionId = form.section_id || allSections[0]?.id || '';
  const grade = Number(form.grade_level);
  const valid = Boolean(form.name.trim()) && form.name.trim().length <= 120 && Number.isInteger(grade) && grade >= 1 && grade <= 12 && allSections.some((s) => s.id === sectionId);
  const create = useMutation({
    mutationFn: (body: { name: string; grade_level: number; section_id: string }) => api<StudentDetail>('/students', { method: 'POST', body }),
    onSuccess: (_student, body) => { qc.invalidateQueries(); toast.success(`Added ${body.name}`); onClose(); },
    onSettled: () => { busy.current = false; },
  });
  const close = () => { if (!busy.current) onClose(); };
  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { if (busy.current) return; create.reset(); setForm((f) => ({ ...f, [k]: e.target.value })); };
  return (
    <Modal title="Add student" onClose={close}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); if (!valid || busy.current) return; busy.current = true; create.mutate({ name: form.name.trim(), grade_level: grade, section_id: sectionId }); }}>
        <label className="field">Name<input className="input" autoFocus required maxLength={120} disabled={create.isPending} value={form.name} onChange={set('name')} /></label>
        <label className="field">Grade level
          <select className="input" disabled={create.isPending} value={form.grade_level} onChange={set('grade_level')}>{[...Array(12)].map((_, i) => <option key={i + 1}>{i + 1}</option>)}</select>
        </label>
        <label className="field">Section
          <select className="input" required disabled={create.isPending} value={sectionId} onChange={set('section_id')}>
            {courses.map((c) => <optgroup key={c.id} label={c.name}>{c.sections.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</optgroup>)}
          </select>
        </label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" disabled={create.isPending} onClick={close}>Cancel</button>
          <button className="btn primary" disabled={create.isPending || !valid}>Add student</button>
        </div>
      </form>
    </Modal>
  );
}

export function NewClassDialog({ onClose }: DialogProps) {
  const { courses } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const busy = useRef(false);
  const [courseId, setCourseId] = useState('');
  const [name, setName] = useState('');
  const valid = Boolean(name.trim()) && name.trim().length <= (courseId ? 60 : 120) && (!courseId || courses.some((c) => c.id === courseId));
  const create = useMutation<CourseOut | SectionOut, Error, { courseId: string; name: string }>({
    mutationFn: ({ courseId, name }) => courseId
      ? api<SectionOut>('/sections', { method: 'POST', body: { course_id: courseId, name } })
      : api<CourseOut>('/courses', { method: 'POST', body: { name, initial_section_name: 'Period 1' } }),
    onSuccess: (_result, body) => { qc.invalidateQueries(); toast.success(body.courseId ? `Added section ${body.name}` : `Added ${body.name}`); onClose(); },
    onSettled: () => { busy.current = false; },
  });
  const close = () => { if (!busy.current) onClose(); };
  return (
    <Modal title="Add course or section" onClose={close}>
      <form className="grid" onSubmit={(e) => { e.preventDefault(); if (!valid || busy.current) return; busy.current = true; create.mutate({ courseId, name: name.trim() }); }}>
        <label className="field">Add to
          <select className="input" disabled={create.isPending} value={courseId} onChange={(e) => { if (busy.current) return; create.reset(); setCourseId(e.target.value); }}>
            <option value="">New course…</option>
            {courses.map((c) => <option key={c.id} value={c.id}>{c.name} (new section)</option>)}
          </select>
        </label>
        <label className="field">{courseId ? 'Section name' : 'Course name'}
          <input className="input" required autoFocus maxLength={courseId ? 60 : 120} disabled={create.isPending} value={name} onChange={(e) => { if (busy.current) return; create.reset(); setName(e.target.value); }} placeholder={courseId ? 'Period 6' : 'Chemistry'} />
        </label>
        <ErrorBox error={create.error} />
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" disabled={create.isPending} onClick={close}>Cancel</button>
          <button className="btn primary" disabled={create.isPending || !valid}>Create</button>
        </div>
      </form>
    </Modal>
  );
}

export function ImportDialog({ onClose }: DialogProps) {
  const { allSections } = useScope();
  const qc = useQueryClient();
  const busy = useRef(false);
  const fileRead = useRef(0);
  const reading = useRef(false);
  const [isReading, setIsReading] = useState(false);
  const [fileError, setFileError] = useState<Error | null>(null);
  const [sectionId, setSectionId] = useState(allSections[0]?.id ?? '');
  const [text, setText] = useState('');
  useEffect(() => () => { fileRead.current += 1; }, []);
  const run = useMutation({
    mutationFn: ({ sectionId, csv }: { sectionId: string; csv: string }) => api<ImportResult>(`/sections/${sectionId}/import`, { method: 'POST', body: { csv } }),
    onSuccess: () => qc.invalidateQueries(),
    onSettled: () => { busy.current = false; },
  });
  const resetDraft = () => {
    fileRead.current += 1;
    reading.current = false;
    setIsReading(false);
    setFileError(null);
    run.reset();
  };
  const close = () => { if (!busy.current) { fileRead.current += 1; onClose(); } };
  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || busy.current) return;
    resetDraft();
    const request = fileRead.current;
    reading.current = true;
    setIsReading(true);
    setText('');
    try {
      const csv = await file.text();
      if (request === fileRead.current) setText(csv);
    } catch (error) {
      if (request === fileRead.current) setFileError(new Error(`Could not read CSV file: ${error instanceof Error ? error.message : 'Please try again.'}`));
    } finally {
      if (request === fileRead.current) { reading.current = false; setIsReading(false); }
    }
  };
  const valid = Boolean(text.trim()) && allSections.some((s) => s.id === sectionId);
  return (
    <Modal title="Import students from CSV" onClose={close}>
      <div className="grid">
        <label className="field">Section
          <select className="input" disabled={run.isPending} value={sectionId} onChange={(e) => { if (busy.current) return; resetDraft(); setSectionId(e.target.value); }}>
            {allSections.map((s) => <option key={s.id} value={s.id}>{s.course} · {s.name}</option>)}
          </select>
        </label>
        <label className="field">CSV file (columns: name, grade_level)<input className="input" type="file" accept=".csv,text/csv" disabled={run.isPending} onChange={onFile} /></label>
        <textarea className="input" rows={5} disabled={run.isPending} value={text} onChange={(e) => { if (busy.current) return; resetDraft(); setText(e.target.value); }} placeholder={'name,grade_level\nAda Lovelace,10'} aria-label="CSV text" />
        {isReading && <div role="status">Reading CSV file…</div>}
        <ErrorBox error={fileError ?? run.error} />
        {run.data && <div role="status"><strong>{run.data.created} added.</strong>{run.data.skipped.length > 0 && <ul>{run.data.skipped.map((m) => <li key={m} className="muted">{m}</li>)}</ul>}</div>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn" disabled={run.isPending} onClick={close}>{run.data ? 'Done' : 'Cancel'}</button>
          <button type="button" className="btn primary" disabled={run.isPending || isReading || !valid} onClick={() => { if (busy.current || reading.current || !valid) return; busy.current = true; run.mutate({ sectionId, csv: text }); }}>Import</button>
        </div>
      </div>
    </Modal>
  );
}

const VALID_SORT = new Set<string>(COLS.map(([k]) => k));
function isSortKey(value: string | null): value is SortKey {
  return value !== null && VALID_SORT.has(value);
}

export default function Roster() {
  const { course, section } = useScope();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState<'student' | 'class' | 'import' | null>(null);

  // Filters live in the URL so a refresh, back button or shared link keeps the view.
  const search = params.get('q') ?? '';
  const risk = FILTERS.some(([v]) => v === params.get('status')) ? params.get('status') ?? '' : '';
  const requestedSort = params.get('sort');
  const sort: { key: SortKey; dir: number } = { key: isSortKey(requestedSort) ? requestedSort : 'risk', dir: params.get('dir') === 'desc' ? -1 : 1 };
  const update = (patch: Record<string, string>) => setParams((p) => {
    const n = new URLSearchParams(p);
    if (!('page' in patch)) n.delete('page');
    Object.entries(patch).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)));
    return n;
  }, { replace: true });

  const q = useQuery({
    queryKey: ['students', course?.id, section?.id],
    queryFn: ({ signal }) => api<StudentSummary[]>(`/students?${new URLSearchParams({ ...(course && { course_id: course.id }), ...(section && { section_id: section.id }) })}`, { signal }),
  });
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const get = (r: StudentSummary) => sort.key === 'risk' ? RISK_ORDER[r.risk] : sort.key === 'section' ? `${r.course} ${r.section}` : sort.key === 'name' ? r.name.toLowerCase() : r[sort.key];
    return (q.data ?? [])
      .filter((r) => (!risk || r.risk === risk) && (!term || r.name.toLowerCase().includes(term)))
      .sort((a, b) => {
        const [x, y] = [get(a), get(b)];
        if (x == null && y == null) return 0;
        if (x == null) return 1; if (y == null) return -1;   // empty values always last
        return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
      });
  }, [q.data, search, risk, sort.key, sort.dir]);
  const pageSize = 50;
  const requestedPage = Number(params.get('page') ?? '1');
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(pages, Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1);
  const visibleRows = rows.slice((page - 1) * pageSize, page * pageSize);
  const toggleSort = (key: SortKey) => {
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
              {visibleRows.map((r) => (
                <tr key={r.id} className="link" onClick={(e) => { if (!(e.target instanceof Element && e.target.closest('a'))) nav(`/students/${r.id}`); }}>
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
          {rows.length > pageSize && <nav className="row" aria-label="Roster pages" style={{ padding: 12, justifyContent: 'space-between' }}>
            <button type="button" className="btn" disabled={page === 1} onClick={() => update({ page: page === 2 ? '' : String(page - 1) })}>Previous page</button>
            <span aria-live="polite">{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, rows.length)} of {rows.length} · Page {page} of {pages}</span>
            <button type="button" className="btn" disabled={page === pages} onClick={() => update({ page: String(page + 1) })}>Next page</button>
          </nav>}
        </div>
      )}
      {dialog === 'student' && <NewStudentDialog onClose={() => setDialog(null)} />}
      {dialog === 'import' && <ImportDialog onClose={() => setDialog(null)} />}
      {dialog === 'class' && <NewClassDialog onClose={() => setDialog(null)} />}
    </>
  );
}
