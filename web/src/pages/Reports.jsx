import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, fmt } from '../api';
import { useActiveSection, useScope } from '../scope';
import { ScopePicker } from '../App';
import { ErrorBox, Loading, RiskChip, Stat } from '../components/ui';
import '../reports.css';

const tone = (pct) => (pct >= 80 ? 'good' : pct >= 70 ? 'warn' : 'bad');
const TONES = [['warm', 'Warm'], ['neutral', 'Neutral'], ['concerned', 'Concerned']];
const shortDay = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

/** Horizontal bars: one row per assessment, class average of max points. */
function AssessmentBars({ rows }) {
  const graded = rows.filter((r) => r.average != null);
  if (!graded.length) return <p className="muted">No graded work yet.</p>;
  const ROW = 30, LABEL = 150, W = 520, BAR = W - LABEL - 44;
  const label = (t) => (t.length > 22 ? `${t.slice(0, 21)}…` : t);
  return (
    <>
      <svg className="rep-chart" viewBox={`0 0 ${W} ${graded.length * ROW + 4}`} role="img"
        aria-label={`Class average by assessment: ${graded.map((r) => `${r.title} ${Math.round(r.average)} percent`).join(', ')}`}>
        {graded.map((r, i) => (
          <g key={r.id} transform={`translate(0 ${i * ROW})`}>
            <title>{`${r.title}: average ${fmt(r.average, '%')}, median ${fmt(r.median, '%')}, range ${fmt(r.min)}-${fmt(r.max, '%')}, ${fmt(r.missing_pct, '%')} missing`}</title>
            <text x={LABEL - 8} y={19} textAnchor="end">{label(r.title)}</text>
            <rect className="track" x={LABEL} y={7} width={BAR} height={14} rx={4} />
            <rect className={tone(r.average)} x={LABEL} y={7} width={Math.max(2, (BAR * r.average) / 100)} height={14} rx={4} />
            <text className="dim" x={LABEL + BAR + 6} y={19}>{fmt(r.average, '%')}</text>
          </g>
        ))}
      </svg>
      <div className="rep-legend" aria-hidden="true">
        <span><i style={{ background: 'var(--good)' }} />80%+</span>
        <span><i style={{ background: 'var(--warn)' }} />70-79%</span>
        <span><i style={{ background: 'var(--bad)' }} />under 70%</span>
      </div>
    </>
  );
}

/** One column per marked day; height is the attendance rate. */
function AttendanceStrip({ days }) {
  if (!days.length) return <p className="muted">No attendance recorded in the last 30 days.</p>;
  const H = 90, COL = 18, W = Math.max(days.length * COL, 120);
  return (
    <>
      <div className="table-wrap">
        <svg className="rep-chart" style={{ minWidth: W }} viewBox={`0 0 ${W} ${H + 18}`} role="img"
          aria-label={`Daily attendance rate over the last 30 days: ${days.map((d) => `${shortDay(d.day)} ${d.rate == null ? 'no data' : `${Math.round(d.rate)} percent`}`).join(', ')}`}>
          <line className="axis" x1="0" x2={W} y1={H} y2={H} />
          {days.map((d, i) => (
            <g key={d.day}>
              <title>{`${shortDay(d.day)}: ${fmt(d.rate, '%')} attended, ${d.absent} absent`}</title>
              <rect className={d.rate == null ? 'track' : tone(d.rate)} x={i * COL + 2} width={COL - 4} rx={3}
                y={H - (d.rate == null ? 4 : Math.max(3, (H * d.rate) / 100))} height={d.rate == null ? 4 : Math.max(3, (H * d.rate) / 100)} />
            </g>
          ))}
          <text className="dim" x="0" y={H + 14}>{shortDay(days[0].day)}</text>
          <text className="dim" x={W} y={H + 14} textAnchor="end">{shortDay(days[days.length - 1].day)}</text>
        </svg>
      </div>
    </>
  );
}

function Summary({ section }) {
  const q = useQuery({ queryKey: ['report-summary', section.id], queryFn: () => api(`/reports/sections/${section.id}/summary`) });
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const s = q.data;
  if (!s) return null;
  if (!s.students) return <div className="card empty">No students in this section yet. Add some on the roster.</div>;
  return (
    <>
      <div className="grid stats">
        <Stat label="Students" value={s.students} />
        <Stat label="Class average" value={fmt(s.average, '%')} />
        <Stat label="Attendance" value={fmt(s.attendance_rate, '%')} />
        <Stat label="Need attention" value={s.attention.length} />
      </div>
      <div className="rep-grid">
        <section className="card" aria-labelledby="rep-assess">
          <h2 id="rep-assess">Assessment averages</h2>
          <AssessmentBars rows={s.assessments} />
          {s.assessments.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary>Show the numbers</summary>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Assessment</th><th>Avg</th><th>Median</th><th>Min</th><th>Max</th><th>Missing</th></tr></thead>
                  <tbody>
                    {s.assessments.map((a) => (
                      <tr key={a.id}><td>{a.title}</td><td className="num">{fmt(a.average, '%')}</td><td className="num">{fmt(a.median, '%')}</td>
                        <td className="num">{fmt(a.min, '%')}</td><td className="num">{fmt(a.max, '%')}</td><td className="num">{fmt(a.missing_pct, '%')}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </section>
        <section className="card" aria-labelledby="rep-att">
          <h2 id="rep-att">Attendance, last 30 days</h2>
          <AttendanceStrip days={s.attendance} />
          <h2 style={{ marginTop: 18 }}>Grade distribution</h2>
          <div className="rep-dist">
            {Object.entries(s.distribution).map(([k, v]) => <span key={k} className={`chip ${k === 'A' || k === 'B' ? 'good' : k === 'C' ? 'warn' : k === 'D' || k === 'F' ? 'bad' : 'neutral'}`}>{k}: {v}</span>)}
          </div>
        </section>
        <section className="card" aria-labelledby="rep-attn">
          <h2 id="rep-attn">Students needing attention</h2>
          {s.attention.length === 0 ? <p className="muted">Nobody is flagged right now.</p> : (
            <ul className="rep-attn">
              {s.attention.map((a) => (
                <li key={a.id}><RiskChip risk={a.risk} /><span><strong>{a.name}</strong> <span className="muted num">{fmt(a.average, '%')}</span></span>
                  {a.reasons.length > 0 && <span className="why">{a.reasons.join(' · ')}</span>}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function ParentComposer({ section }) {
  const students = useQuery({ queryKey: ['students', { section: section.id }], queryFn: () => api(`/students?section_id=${section.id}`) });
  const [studentId, setStudentId] = useState('');
  const [toneSel, setTone] = useState('warm');
  const [draft, setDraft] = useState(null); // {subject, body, source}
  const [copied, setCopied] = useState(false);
  useEffect(() => { setStudentId(''); setDraft(null); }, [section.id]);
  const gen = useMutation({
    mutationFn: () => api(`/reports/students/${studentId}/parent-update`, { method: 'POST', body: { tone: toneSel } }),
    onSuccess: (d) => { setDraft(d); setCopied(false); },
  });
  const list = students.data ?? [];
  const copy = async () => {
    try { await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* clipboard blocked */ }
  };
  const mailto = draft ? `mailto:?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}` : '#';
  return (
    <section className="card rep-composer" aria-labelledby="rep-parent">
      <div className="rep-head"><h2 id="rep-parent">Parent update</h2>{draft && <span className="chip neutral">{draft.source === 'ai' ? 'AI draft' : 'Template draft'}</span>}</div>
      <p className="rep-privacy">Drafts use only this student&apos;s grades and attendance. Review and edit before sending; nothing is sent from here.</p>
      <ErrorBox error={students.error || gen.error} />
      {!students.isLoading && list.length === 0 ? <p className="muted">Add students to this section to draft updates.</p> : (
        <div className="fields">
          <label>Student
            <select className="input" value={studentId} onChange={(e) => { setStudentId(e.target.value); setDraft(null); }}>
              <option value="">Choose a student…</option>
              {list.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label>Tone
            <select className="input" value={toneSel} onChange={(e) => setTone(e.target.value)}>
              {TONES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        </div>
      )}
      <div className="row">
        <button className="btn primary" disabled={!studentId || gen.isPending} onClick={() => gen.mutate()}>{gen.isPending ? 'Drafting…' : draft ? 'Regenerate' : 'Generate draft'}</button>
      </div>
      {draft && (
        <>
          <label>Subject
            <input className="input" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
          </label>
          <label>Message
            <textarea className="input" value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
          </label>
          <div className="row">
            <button className="btn" onClick={copy}>{copied ? 'Copied ✓' : 'Copy'}</button>
            <a className="btn primary" href={mailto}>Open in email</a>
          </div>
          <span className="sr-only" role="status">{copied ? 'Copied to clipboard' : ''}</span>
        </>
      )}
    </section>
  );
}

export default function Reports() {
  const section = useActiveSection();
  const { isLoading } = useScope();
  if (isLoading) return <Loading />;
  if (!section) return <div className="card empty">Create a course and section on the roster first.</div>;
  return (
    <>
      <div className="topbar">
        <div><h1>Reports</h1><div className="page-sub">{section.name} · class snapshot and parent updates</div></div>
        <div className="row">
          <ScopePicker />
          <a className="btn" href={`/api/reports/sections/${section.id}/gradebook.csv`} download>Download CSV</a>
        </div>
      </div>
      <Summary section={section} />
      <ParentComposer section={section} />
    </>
  );
}
