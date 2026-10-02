import type { AttendanceMark, AttendanceSheet, AttendanceStatus } from '../types';
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api';
import { useSchoolCalendar } from '../schoolCalendar';
import { useActiveSection, useScope } from '../scope';
import { Link } from 'react-router-dom';
import ScopePicker from '../components/ScopePicker';
import ScopeStatus from '../components/ScopeStatus';
import { useToast } from '../components/Toast';
import { EmptyState, ErrorBox, Loading } from '../components/ui';

const STATUSES: [AttendanceStatus, string][] = [['present', 'Present'], ['tardy', 'Tardy'], ['absent', 'Absent'], ['excused', 'Excused']];
interface AttendanceChange { sectionId: string; day: string; marks: AttendanceMark[] }

export default function Attendance() {
  const section = useActiveSection();
  const { isLoading: scopeLoading, ready } = useScope();
  const qc = useQueryClient();
  const toast = useToast();
  const calendar = useSchoolCalendar(!!section);
  const [chosenDay, setDay] = useState<string | null>(null);
  const day = chosenDay ?? calendar.data?.today ?? '';
  const key = ['attendance', section?.id, day];
  const q = useQuery({ queryKey: key, queryFn: ({ signal }) => api<AttendanceSheet>(`/sections/${section?.id}/attendance?day=${day}`, { signal }), enabled: !!section && !!day && !!calendar.data });
  const save = useMutation({
    mutationKey: ['attendance-save'],
    scope: { id: 'attendance-save' },
    mutationFn: ({ sectionId, day: markedDay, marks }: AttendanceChange) => api<AttendanceSheet>(`/sections/${sectionId}/attendance`, { method: 'PUT', body: { day: markedDay, marks } }),
    onMutate: async ({ marks, sectionId, day: markedDay }) => {
      const queryKey = ['attendance', sectionId, markedDay];
      await qc.cancelQueries({ queryKey });
      const prev = qc.getQueryData<AttendanceSheet>(queryKey);
      const by = new Map(marks.map((m) => [m.student_id, m.status]));
      qc.setQueryData<AttendanceSheet>(queryKey, (d) => d && ({ ...d, rows: d.rows.map((r) => ({ ...r, status: by.get(r.student_id) ?? r.status })) }));
      return { prev, queryKey };
    },
    onError: (e, { marks }, ctx) => {
      if (ctx?.prev) {
        const by = new Map(marks.map((m) => [m.student_id, m.status]));
        qc.setQueryData<AttendanceSheet>(ctx.queryKey, (d) => d && ({ ...d, rows: d.rows.map((r) => by.has(r.student_id) && r.status === by.get(r.student_id) ? { ...r, status: ctx.prev?.rows.find((old) => old.student_id === r.student_id)?.status ?? null } : r) }));
      }
      toast.error(`Couldn’t save attendance: ${e.message}`);
    },
    onSuccess: (_d, { marks }) => { if (marks.length > 1) toast.success(`Marked ${marks.length} students present`); },
    onSettled: (_data, _error, { sectionId }) => {
      if (qc.isMutating({ mutationKey: ['attendance-save'] }) <= 1) void qc.invalidateQueries({ queryKey: ['attendance'] });
      void qc.invalidateQueries({ queryKey: ['overview'] }); void qc.invalidateQueries({ queryKey: ['students'] }); void qc.invalidateQueries({ queryKey: ['student'] });
      void qc.invalidateQueries({ queryKey: ['report-summary', sectionId], exact: true });
    },
  });
  if (!ready) return <><div className="topbar"><h1>Attendance</h1><ScopePicker /></div><ScopeStatus /></>;
  if (scopeLoading) return <Loading />;
  if (!section) return (
    <>
      <div className="topbar"><h1>Attendance</h1><ScopePicker /></div>
      <ScopeStatus />
      <EmptyState title="No classes yet"><p>Create a course and section to take attendance.</p><div className="row"><Link className="btn primary" to="/roster">Go to roster</Link></div></EmptyState>
    </>
  );
  if (calendar.isLoading) return <><ScopeStatus /><Loading /></>;
  if (!calendar.data) return <><ScopeStatus /><ErrorBox error={calendar.error} onRetry={() => calendar.refetch()} /></>;
  const sheet = q.data;
  const unmarked = sheet?.rows.filter((r) => !r.status) ?? [];
  return (
    <>
      <div className="topbar">
        <div><h1>Attendance</h1><div className="page-sub" aria-live="polite">{section.name} · {sheet ? (unmarked.length ? `${unmarked.length} not yet marked` : 'All marked ✓') : ' '}</div></div>
        <div className="row"><ScopePicker /><input className="input compact" type="date" value={day} max={calendar.data.today} onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="Date" /></div>
      </div>
      <p className="muted">School dates use {calendar.data.timezone}.</p>
      <ScopeStatus />
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {q.isLoading && <Loading />}
      {sheet && sheet.rows.length === 0 && (
        <EmptyState title="No students in this section"><p>Add students to take attendance.</p><div className="row"><Link className="btn primary" to="/roster">Add students</Link></div></EmptyState>
      )}
      {sheet && sheet.rows.length > 0 && (
        <div className="card">
          {unmarked.length > 0 && (
            <div className="row" style={{ marginBottom: 12 }}>
              <button type="button" className="btn" onClick={() => save.mutate({ sectionId: section.id, day, marks: unmarked.map((r) => ({ student_id: r.student_id, status: 'present' })) })}>Mark {unmarked.length} unmarked present</button>
            </div>
          )}
          <table>
            <caption className="sr-only">Attendance for {section.name} on {day}</caption>
            <thead><tr><th scope="col">Student</th><th scope="col" style={{ textAlign: 'right' }}>Attendance status</th></tr></thead>
            <tbody>
              {sheet.rows.map((r) => (
                <tr key={r.student_id}>
                  <th scope="row" className="name">{r.name}</th>
                  <td style={{ textAlign: 'right' }}>
                    <span className="att-btns" role="group" aria-label={`Attendance for ${r.name}`}>
                      {STATUSES.map(([s, l]) => <button type="button" key={s} className={`${s} ${r.status === s ? 'on' : ''}`} aria-pressed={r.status === s} onClick={() => save.mutate({ sectionId: section.id, day, marks: [{ student_id: r.student_id, status: s }] })}>{l}</button>)}
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
