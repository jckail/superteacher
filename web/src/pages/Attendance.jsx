import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { useActiveSection, useScope } from '../scope';
import { Link } from 'react-router-dom';
import ScopePicker from '../components/ScopePicker';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorBox, Loading } from '../components/ui';

const STATUSES = [['present', 'Present'], ['tardy', 'Tardy'], ['absent', 'Absent'], ['excused', 'Excused']];
const today = () => new Date().toISOString().slice(0, 10);

export default function Attendance() {
  const section = useActiveSection();
  const { isLoading: scopeLoading } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const [day, setDay] = useState(today());
  const key = ['attendance', section?.id, day];
  const q = useQuery({ queryKey: key, queryFn: () => api(`/sections/${section.id}/attendance?day=${day}`), enabled: !!section });
  const save = useMutation({
    mutationFn: (marks) => api(`/sections/${section.id}/attendance`, { method: 'PUT', body: { day, marks } }),
    onMutate: async (marks) => {   // optimistic: the click should feel instant
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData(key);
      const by = Object.fromEntries(marks.map((m) => [m.student_id, m.status]));
      qc.setQueryData(key, (d) => ({ ...d, rows: d.rows.map((r) => (by[r.student_id] ? { ...r, status: by[r.student_id] } : r)) }));
      return { prev };
    },
    onError: (e, _v, ctx) => { ctx?.prev && qc.setQueryData(key, ctx.prev); toast.error(`Couldn’t save attendance: ${e.message}`); },
    onSuccess: (_d, marks) => { if (marks.length > 1) toast.success(`Marked ${marks.length} students present`); },
    onSettled: () => { qc.invalidateQueries({ queryKey: ['overview'] }); qc.invalidateQueries({ queryKey: ['students'] }); qc.invalidateQueries({ queryKey: ['student'] }); },
  });
  if (scopeLoading) return <Loading />;
  if (!section) return (
    <>
      <div className="topbar"><h1>Attendance</h1></div>
      <EmptyState title="No classes yet"><p>Create a course and section to take attendance.</p><div className="row"><Link className="btn primary" to="/roster">Go to roster</Link></div></EmptyState>
    </>
  );
  const sheet = q.data;
  const unmarked = sheet?.rows.filter((r) => !r.status) ?? [];
  return (
    <>
      <div className="topbar">
        <div><h1>Attendance</h1><div className="page-sub" aria-live="polite">{section.name} · {sheet ? (unmarked.length ? `${unmarked.length} not yet marked` : 'All marked ✓') : ' '}</div></div>
        <div className="row"><ScopePicker /><input className="input compact" type="date" value={day} max={today()} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Date" /></div>
      </div>
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {q.isLoading && <Loading />}
      {sheet && sheet.rows.length === 0 && (
        <EmptyState title="No students in this section"><p>Add students to take attendance.</p><div className="row"><Link className="btn primary" to="/roster">Add students</Link></div></EmptyState>
      )}
      {sheet && sheet.rows.length > 0 && (
        <div className="card">
          {unmarked.length > 0 && (
            <div className="row" style={{ marginBottom: 12 }}>
              <button type="button" className="btn" onClick={() => save.mutate(unmarked.map((r) => ({ student_id: r.student_id, status: 'present' })))}>Mark {unmarked.length} unmarked present</button>
            </div>
          )}
          <table>
            <caption className="sr-only">Attendance for {section.name} on {day}</caption>
            <tbody>
              {sheet.rows.map((r) => (
                <tr key={r.student_id}>
                  <td className="name">{r.name}</td>
                  <td style={{ textAlign: 'right' }}>
                    <span className="att-btns" role="group" aria-label={`Attendance for ${r.name}`}>
                      {STATUSES.map(([s, l]) => <button type="button" key={s} className={`${s} ${r.status === s ? 'on' : ''}`} aria-pressed={r.status === s} onClick={() => save.mutate([{ student_id: r.student_id, status: s }])}>{l}</button>)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
