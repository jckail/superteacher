import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, fmt } from '../api';
import { ErrorBox, Loading, RiskChip, Sparkline, Stat, gradeColor } from '../components/ui';

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
      <ErrorBox error={q.error} />
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
  const [body, setBody] = useState('');
  const add = useMutation({
    mutationFn: () => api(`/students/${student.id}/notes`, { method: 'POST', body: { body } }),
    onSuccess: () => { setBody(''); qc.invalidateQueries({ queryKey: ['student', student.id] }); qc.invalidateQueries({ queryKey: ['insight', student.id] }); },
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

export default function Student() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['student', id], queryFn: () => api(`/students/${id}`) });
  const del = useMutation({ mutationFn: () => api(`/students/${id}`, { method: 'DELETE' }), onSuccess: () => { qc.invalidateQueries(); nav('/roster'); } });
  const s = q.data;
  if (q.isLoading) return <Loading />;
  if (q.error) return <><Link to="/roster">← Roster</Link><ErrorBox error={q.error} /></>;

  const graded = s.scores.filter((x) => x.pct != null);
  const lastDays = s.attendance.slice(-30);
  return (
    <>
      <Link to="/roster">← Roster</Link>
      <div className="topbar" style={{ marginTop: 8 }}>
        <div>
          <h1>{s.name} <RiskChip risk={s.risk} /></h1>
          <div className="page-sub">Grade {s.grade_level} · {s.course} · {s.section}</div>
        </div>
        <button className="btn danger" onClick={() => confirm(`Remove ${s.name} and all their records?`) && del.mutate()}>Remove student</button>
      </div>
      {s.risk_reasons.length > 0 && <p className="muted">⚑ {s.risk_reasons.join(' · ')}</p>}
      <div className="grid stats">
        <Stat label="Average" value={<span style={{ color: gradeColor(s.average) }}>{fmt(s.average, '%')}</span>} hint={s.letter && `${s.letter} · GPA ${s.gpa?.toFixed(1)}`} />
        <Stat label="Attendance" value={fmt(s.attendance_rate, '%')} hint={`${s.absences} absences · ${s.tardies} tardies`} />
        <Stat label="Homework" value={fmt(s.homework_rate, '%')} hint={s.missing ? `${s.missing} missing` : 'Nothing missing'} />
        <div className="card stat"><div className="label">Score trend</div><div style={{ marginTop: 10 }}><Sparkline values={graded.map((x) => x.pct)} /></div></div>
      </div>
      <div className="grid two">
        <div className="grid">
          <Insight id={s.id} />
          <section className="card">
            <h2>Last {lastDays.length} school days</h2>
            <div className="strip" role="img" aria-label="Attendance history">{lastDays.map((a) => <i key={a.day} className={a.status} title={`${a.day}: ${a.status}`} />)}</div>
            <p className="muted" style={{ fontSize: '.8rem', marginBottom: 0 }}>Green present · amber tardy · grey excused · red absent</p>
          </section>
          <Notes student={s} />
        </div>
        <section className="card table-wrap">
          <h2>Assignments</h2>
          <table>
            <thead><tr><th>Due</th><th>Title</th><th>Score</th></tr></thead>
            <tbody>
              {[...s.scores].reverse().map((x) => (
                <tr key={x.assessment_id}>
                  <td className="muted num">{x.due_date.slice(5)}</td>
                  <td>{x.title} <span className="chip neutral">{x.kind}</span></td>
                  <td className="num">{x.points == null ? <span className="chip bad">missing</span> : <><strong style={{ color: gradeColor(x.pct) }}>{fmt(x.pct, '%')}</strong> <span className="muted">{x.points}/{x.max_points}</span></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
