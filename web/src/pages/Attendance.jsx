import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { useActiveSection, useScope } from '../scope';
import { ScopePicker } from '../App';
import { ErrorBox, Loading } from '../components/ui';

const STATUSES = [['present', 'Present'], ['tardy', 'Tardy'], ['absent', 'Absent'], ['excused', 'Excused']];
const today = () => new Date().toISOString().slice(0, 10);

export default function Attendance() {
  const section = useActiveSection();
  const { isLoading: scopeLoading } = useScope();
  const qc = useQueryClient();
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
    onError: (_e, _v, ctx) => qc.setQueryData(key, ctx.prev),
    onSettled: () => { qc.invalidateQueries({ queryKey: ['overview'] }); qc.invalidateQueries({ queryKey: ['students'] }); qc.invalidateQueries({ queryKey: ['student'] }); },
  });
  if (scopeLoading) return <Loading />;
  if (!section) return <div className="card empty">Create a course and section on the roster first.</div>;
  const sheet = q.data;
  const unmarked = sheet?.rows.filter((r) => !r.status) ?? [];
  return (
    <>
      <div className="topbar">
        <div><h1>Attendance</h1><div className="page-sub">{section.name} · {sheet ? (unmarked.length ? `${unmarked.length} not yet marked` : 'All marked ✓') : ' '}</div></div>
        <div className="row"><ScopePicker /><input className="input compact" type="date" value={day} max={today()} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Date" /></div>
      </div>
      <ErrorBox error={q.error || save.error} />
      {q.isLoading && <Loading />}
      {sheet && (
        <div className="card">
          {unmarked.length > 0 && (
            <div className="row" style={{ marginBottom: 12 }}>
              <button className="btn" onClick={() => save.mutate(unmarked.map((r) => ({ student_id: r.student_id, status: 'present' })))}>Mark {unmarked.length} unmarked present</button>
            </div>
          )}
          <table>
            <tbody>
              {sheet.rows.map((r) => (
                <tr key={r.student_id}>
                  <td className="name">{r.name}</td>
                  <td style={{ textAlign: 'right' }}>
                    <span className="att-btns" role="group" aria-label={`Attendance for ${r.name}`}>
                      {STATUSES.map(([s, l]) => <button key={s} className={`${s} ${r.status === s ? 'on' : ''}`} aria-pressed={r.status === s} onClick={() => save.mutate([{ student_id: r.student_id, status: s }])}>{l}</button>)}
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
