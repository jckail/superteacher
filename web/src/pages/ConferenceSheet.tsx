import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api';
import { useSchoolCalendar } from '../schoolCalendar';
import { ErrorBox, Loading } from '../components/ui';
import type { StudentDetail } from '../types';
import '../conference.css';

const number = (value: number | null, suffix = '') => value === null ? 'Not enough data' : `${Number(value.toFixed(1))}${suffix}`;

export default function ConferenceSheet() {
  const { id } = useParams();
  return <Conference key={id} id={id} />;
}

function Conference({ id }: { id: string | undefined }) {
  const student = useQuery({ queryKey: ['student', id], queryFn: ({ signal }) => api<StudentDetail>(`/students/${id}`, { signal }), enabled: Boolean(id), retry: false, refetchOnMount: 'always' });
  const calendar = useSchoolCalendar(Boolean(id));
  const client = useQueryClient();
  const [approval, setApproval] = useState({ client, notes: {} as Record<string, string> });
  const notes = approval.client === client ? approval.notes : {};
  const [excluded, setExcluded] = useState<string[]>([]);
  const [fits, setFits] = useState(false);
  const paper = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const s = student.data?.id === id ? student.data : undefined;
  const current = Boolean(s && calendar.data && s.as_of === calendar.data.today && !student.isFetching && !calendar.isFetching && !student.isPaused && !calendar.isPaused && !student.error && !calendar.error);
  const missing = s?.scores.filter(score => score.points === null && score.due_date <= s.as_of) ?? [];
  const selectedNotes = s?.notes.filter(note => notes[note.id] === note.body) ?? [];
  const selectedMissing = missing.filter(score => !excluded.includes(score.assessment_id));
  // Observe the content as well as the fixed paper: note changes and font loading can change fit.
  useLayoutEffect(() => {
    const measure = () => {
      const node = paper.current;
      setFits(Boolean(node && node.clientHeight > 0 && node.scrollHeight <= node.clientHeight + 1 && node.scrollWidth <= node.clientWidth + 1));
    };
    measure();
    const observer = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(measure);
    if (paper.current) observer?.observe(paper.current);
    if (content.current) observer?.observe(content.current);
    window.addEventListener('resize', measure);
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure); };
  }, [s, approval, excluded, student.error, calendar.error]);
  // Changed or removed notes permanently lose approval, even if later restored.
  useEffect(() => {
    if (!s) return;
    setApproval(old => ({ client, notes: old.client === client ? Object.fromEntries(Object.entries(old.notes).filter(([noteId, body]) => s.notes.some(note => note.id === noteId && note.body === body))) : {} }));
  }, [s, client]);
  const ready = current && fits;
  return <div className={`conference-page ${ready ? 'conference-ready' : ''}`}>
    <div className="conference-controls">
      <Link className="back" to="/roster">← Roster</Link>
      <h1>Conference sheet</h1>
      <p>Review the summary, then print or save it as a PDF. Private notes are excluded until you choose them.</p>
      {student.isLoading && <Loading />}
      <ErrorBox error={student.error ?? calendar.error} onRetry={() => { void student.refetch(); void calendar.refetch(); }} />
      {student.isSuccess && !s && <p role="status">The requested student summary is unavailable. Refresh before printing.</p>}
      {s && !student.error && <>
        {!current && <p role="status">Checking the current school day. Refresh before printing if this summary is out of date.</p>}
        <button className="btn" type="button" disabled={student.isFetching || calendar.isFetching} onClick={() => { void student.refetch(); void calendar.refetch(); }}>Refresh summary</button>
        <fieldset><legend>Missing work to include ({selectedMissing.length} of {missing.length})</legend>
          {missing.map(score => <label key={score.assessment_id}><input type="checkbox" checked={!excluded.includes(score.assessment_id)} onChange={e => setExcluded(old => e.target.checked ? old.filter(value => value !== score.assessment_id) : [...old, score.assessment_id])} /> {score.title} · due {score.due_date}</label>)}
          {!missing.length && <p>No unscored assignments due by {s.as_of}.</p>}
        </fieldset>
        <fieldset><legend>Private notes to include</legend>
          <p>Only checked notes appear on the sheet. Changed notes need your approval again.</p>
          {s.notes.map(note => <label key={note.id}><input type="checkbox" checked={notes[note.id] === note.body} onChange={e => setApproval(old => { const next = old.client === client ? { ...old.notes } : {}; if (e.target.checked) next[note.id] = note.body; else delete next[note.id]; return { client, notes: next }; })} /> {note.body}</label>)}
          {!s.notes.length && <p>No private notes.</p>}
        </fieldset>
        {current && !fits && <p role="status">The summary exceeds one page. Include fewer assignments or notes before printing.</p>}
      </>}
      <button className="btn primary" type="button" disabled={!ready} onClick={() => {
        const node = paper.current;
        if (current && node && node.clientHeight > 0 && node.scrollHeight <= node.clientHeight + 1 && node.scrollWidth <= node.clientWidth + 1) window.print();
        else setFits(false);
      }}>Print conference sheet</button>
    </div>
    <p className="conference-print-warning">Refresh the summary and choose content that fits one page before printing.</p>
    {s && !student.error && <div className="conference-preview" role="region" aria-label="Printable conference summary" tabIndex={0}>
      <article className="conference-sheet" ref={paper} aria-label={`Conference summary for ${s.name}`}><div ref={content}>
        <h2>{s.name}</h2>
        <p>Grade {s.grade_level} · {s.course} · {s.section}</p>
        <p>Conference summary · as of {s.as_of}</p>
        <dl className="conference-metrics">
          <div><dt>Average</dt><dd>{number(s.average, '%')}{s.letter ? ` (${s.letter})` : ''}</dd></div>
          <div><dt>Grade trend</dt><dd>{s.trend === null ? 'Not enough data' : `${s.trend > 0 ? '+' : ''}${number(s.trend)} percentage points`}</dd></div>
          <div><dt>Attendance</dt><dd>{number(s.attendance_rate, '%')}</dd></div>
          <div><dt>Absences / tardies</dt><dd>{s.absences} / {s.tardies}</dd></div>
        </dl>
        <h3>Missing work</h3>
        <p>{missing.length} unscored assignments due by {s.as_of}. {selectedMissing.length} included below.</p>
        {selectedMissing.length > 0 && <ul>{selectedMissing.map(score => <li key={score.assessment_id}>{score.title} · {score.kind} · due {score.due_date}</li>)}</ul>}
        <h3>Teacher-selected notes</h3>
        {selectedNotes.length ? selectedNotes.map(note => <p className="conference-note" key={note.id}>{note.body}</p>) : <p>No notes selected.</p>}
      </div></article>
    </div>}
  </div>;
}
