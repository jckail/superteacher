import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, fmt } from '../api';
import { useConfirm } from '../components/Confirm';
import { useToast } from '../components/Toast';
import { AttendanceHeat, TrendChart } from '../components/charts';
import { EmptyState, ErrorBox, Loading, RiskChip, Stat, gradeColor } from '../components/ui';

function Insight({ id }) {
  const q = useQuery({ queryKey: ['insight', id], queryFn: () => api(`/students/${id}/insight`), staleTime: 5 * 60_000 });
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
          {[['Strengths', i.strengths], ['Concerns', i.concerns], ['Suggested actions', i.actions]].map(([t, items]) => items.length > 0 && (
            <div key={t}><h3>{t}</h3><ul>{items.map((x) => <li key={x}>{x}</li>)}</ul></div>
          ))}
          {i.source === 'rules' && <p className="muted" style={{ fontSize: '.85rem' }}>Set <code>ANTHROPIC_API_KEY</code> on the server for AI-written insights.</p>}
        </>
      )}
    </section>
  );
}

function Notes({ student }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [body, setBody] = useState('');
  const add = useMutation({
    mutationFn: () => api(`/students/${student.id}/notes`, { method: 'POST', body: { body } }),
    onSuccess: () => { setBody(''); toast.success('Note added'); qc.invalidateQueries({ queryKey: ['student', student.id] }); qc.invalidateQueries({ queryKey: ['insight', student.id] }); },
  });
  return (
    <section className="card">
      <h2>Notes</h2>
      <form className="row" onSubmit={(e) => { e.preventDefault(); body.trim() && add.mutate(); }}>
        <input className="input" style={{ flex: 1 }} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add a private note…" aria-label="New note" />
        <button className="btn" disabled={add.isPending || !body.trim()}>Add</button>
      </form>
      <ErrorBox error={add.error} />
      {student.notes.map((n) => (
        <div className="note" key={n.id}>{n.body}<div className="muted" style={{ fontSize: '.8rem' }}>{new Date(n.created_at).toLocaleDateString()}</div></div>
      ))}
    </section>
  );
}

const short = (d) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

export default function Student() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [kind, setKind] = useState('');
  const q = useQuery({ queryKey: ['student', id], queryFn: () => api(`/students/${id}`), retry: (n, e) => e?.status !== 404 && n < 1 });
  const del = useMutation({
    mutationFn: () => api(`/students/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries(); toast.success('Student removed'); nav('/roster'); },
    onError: (e) => toast.error(`Couldn’t remove student: ${e.message}`),
  });
  const s = q.data;
  const kinds = useMemo(() => [...new Set((s?.scores ?? []).map((x) => x.kind))], [s]);
  if (q.isLoading) return <Loading />;
  if (q.error?.status === 404 || (q.error && !s && /not found/i.test(q.error.message))) {
    return (
      <>
        <Link className="back" to="/roster">← Roster</Link>
        <EmptyState title="Student not found"><p>This student may have been removed.</p><div className="row"><Link className="btn primary" to="/roster">Back to roster</Link></div></EmptyState>
      </>
    );
  }
  if (q.error) return <><Link className="back" to="/roster">← Roster</Link><ErrorBox error={q.error} onRetry={() => q.refetch()} /></>;

  const graded = s.scores.filter((x) => x.pct != null);
  const lastDays = s.attendance.slice(-30);
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
        <button type="button" className="btn danger" onClick={remove} disabled={del.isPending}>Remove student</button>
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
          <Notes student={s} />
        </div>
        <section className="card table-wrap">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <h2>Assignments</h2>
            {kinds.length > 1 && (
              <div className="seg" role="group" aria-label="Filter by type">
                {[['', 'All'], ...kinds.map((k) => [k, k])].map(([v, l]) => <button type="button" key={v} className={kind === v ? 'on' : ''} aria-pressed={kind === v} onClick={() => setKind(v)}>{l}</button>)}
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
                    <td className="num">{x.points == null ? <span className="chip bad">missing</span> : <><strong style={{ color: gradeColor(x.pct) }}>{fmt(x.pct, '%')}</strong> <span className="muted">{x.points}/{x.max_points}</span></>}</td>
                  </tr>
                ))}
                {shown.length === 0 && <tr><td colSpan={3} className="empty">Nothing of this type.</td></tr>}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}
