import type { AssessmentStat, AttendanceDay, ClassSummary, ParentUpdateIn, ParentUpdateOut, Section, Tone } from '../types';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ApiError, api, fmt } from '../api';
import { useActiveSection, useScope } from '../scope';
import ScopePicker from '../components/ScopePicker';
import ScopeStatus from '../components/ScopeStatus';
import { useRosterPage } from '../useRosterPage';
import { ErrorBox, Loading, RiskChip, Stat } from '../components/ui';
import '../reports.css';

const tone = (pct: number) => (pct >= 80 ? 'good' : pct >= 70 ? 'warn' : 'bad');
const TONES: [Tone, string][] = [['warm', 'Warm'], ['neutral', 'Neutral'], ['concerned', 'Concerned']];
const shortDay = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

/** Horizontal bars: one row per assessment, class average of max points. */
function AssessmentBars({ rows }: { rows: AssessmentStat[] }) {
  const graded = rows.filter((r): r is AssessmentStat & { average: number } => r.average != null);
  if (!graded.length) return <p className="muted">No graded work yet.</p>;
  const ROW = 30, LABEL = 150, W = 520, BAR = W - LABEL - 44;
  const label = (t: string) => (t.length > 22 ? `${t.slice(0, 21)}…` : t);
  return (
    <>
      <svg className="rep-chart" viewBox={`0 0 ${W} ${graded.length * ROW + 4}`} role="img"
        aria-label={`Class average by assessment: ${graded.map((r) => `${r.title} ${Math.round(r.average)} percent`).join(', ')}`}>
        {graded.map((r, i) => (
          <g key={r.id} transform={`translate(0 ${i * ROW})`}>
            <title>{`${r.title}: average ${fmt(r.average, '%')}, median ${fmt(r.median, '%')}, range ${fmt(r.min)}-${fmt(r.max, '%')}, ${fmt(r.missing_pct, '%')} missing`}</title>
            <text x={LABEL - 8} y={19} textAnchor="end">{label(r.title)}</text>
            <rect className="track" x={LABEL} y={7} width={BAR} height={14} rx={4} />
            <rect className={tone(r.average)} x={LABEL} y={7} width={Math.max(2, (BAR * Math.min(r.average, 100)) / 100)} height={14} rx={4} />
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
function AttendanceStrip({ days }: { days: AttendanceDay[] }) {
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

function Summary({ section }: { section: Section }) {
  const { setSection } = useScope();
  const q = useQuery({ queryKey: ['report-summary', section.id], queryFn: ({ signal }) => api<ClassSummary>(`/reports/sections/${section.id}/summary`, { signal }) });
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
        <Stat label="Not enough data" value={s.unknown} hint="Work or attendance evidence needed" />
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
          {s.unknown > 0 && <p className="muted">{s.unknown} student{s.unknown === 1 ? '' : 's'} lack{s.unknown === 1 ? 's' : ''} enough data to assess progress. <Link to="/roster?status=unknown" onClick={() => setSection(section.id)}>Review records needing data</Link>.</p>}
          {s.attention.length === 0 ? <p className="muted">{s.unknown === s.students ? 'Record work or attendance before assessing progress.' : s.unknown ? 'No attention flags among students with evidence.' : 'Nobody is flagged right now.'}</p> : (
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

type SelectedStudent = { id: string; name: string; sectionId: string };
type GenerationGate = { pending: boolean; start: (work: () => Promise<void>) => void };

function ParentComposer({ section, generation }: { section: Section; generation: GenerationGate }) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<SelectedStudent | null>(null);
  const [toneSel, setTone] = useState<Tone>('warm');
  const [draft, setDraft] = useState<ParentUpdateOut | null>(null);
  const [generationError, setGenerationError] = useState<Error | null>(null);
  const [copied, setCopied] = useState(false);
  const lifecycle = useRef({ mounted: true, revision: 0, request: 0, draftRevision: 0, copyOperation: 0, timer: undefined as ReturnType<typeof setTimeout> | undefined });
  const clearCopied = useCallback(() => {
    const state = lifecycle.current;
    state.copyOperation += 1;
    state.draftRevision += 1;
    clearTimeout(state.timer);
    state.timer = undefined;
    setCopied(false);
  }, []);
  const reset = useCallback(() => {
    lifecycle.current.revision += 1;
    clearCopied();
    setSelected(null);
    setDraft(null);
    setGenerationError(null);
  }, [clearCopied]);
  const students = useRosterPage({ enabled: true, sectionId: section.id, search, risk: '', sort: 'name', direction: 'asc' }, reset);
  useEffect(() => {
    const state = lifecycle.current;
    state.mounted = true;
    return () => { state.mounted = false; state.revision += 1; state.copyOperation += 1; clearTimeout(state.timer); };
  }, []);
  useEffect(() => { if (students.data?.total_scoped === 0) reset(); }, [students.data?.total_scoped, reset]);
  const list = students.data?.items ?? [];
  const pinned = selected && !list.some((s) => s.id === selected.id);
  const generate = () => {
    if (!selected || selected.sectionId !== section.id || generation.pending) return;
    const state = lifecycle.current;
    const revision = state.revision;
    const captured = selected;
    const tone = toneSel;
    generation.start(async () => {
      const request = ++state.request;
      setGenerationError(null);
      const current = () => state.mounted && state.revision === revision && state.request === request;
      try {
        const body: ParentUpdateIn = { tone, expected_section_id: captured.sectionId };
        const result = await api<ParentUpdateOut>(`/reports/students/${captured.id}/parent-update`, { method: 'POST', body });
        if (current()) { clearCopied(); setDraft(result); }
      } catch (error) {
        if (current()) {
          if (error instanceof ApiError && error.status === 404) reset();
          setGenerationError(error instanceof Error ? error : new Error('Unable to generate this draft. Please try again.'));
        }
      }
    });
  };
  const copy = async () => {
    if (!draft) return;
    const state = lifecycle.current;
    const revision = state.draftRevision;
    const operation = ++state.copyOperation;
    clearTimeout(state.timer);
    setCopied(false);
    const current = () => state.mounted && state.draftRevision === revision && state.copyOperation === operation;
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      if (!current()) return;
      setCopied(true);
      state.timer = setTimeout(() => { if (current()) setCopied(false); }, 2000);
    } catch { /* clipboard blocked */ }
  };
  const edit = (value: ParentUpdateOut) => { clearCopied(); setDraft(value); };
  const mailto = draft ? `mailto:?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}` : '#';
  return (
    <section className="card rep-composer" aria-labelledby="rep-parent">
      <div className="rep-head"><h2 id="rep-parent">Parent update</h2>{draft && <span className="chip neutral">{draft.source === 'ai' ? 'AI draft' : 'Template draft'}</span>}</div>
      <p className="rep-privacy">Drafts use only this student&apos;s grades and attendance. Review and edit before sending; nothing is sent from here.</p>
      <label>Search students<input className="input" type="search" maxLength={120} value={search} onChange={(e) => setSearch(e.target.value)} /></label>
      {search && <button className="btn" onClick={() => setSearch('')}>Clear search</button>}
      <ErrorBox error={students.error} />
      {students.error && <button className="btn" onClick={() => { if (students.invalidCursor) students.restart(); else void students.retry(); }}>{students.invalidCursor ? 'Restart student list' : 'Retry student list'}</button>}
      {students.loading && <p role="status">Loading students…</p>}
      {students.data && <p role="status">{students.data.total_matches} matching students · {students.data.total_scoped} in this section · Page {students.page}</p>}
      {students.data?.total_scoped === 0 && <p className="muted">Add students to this section to draft updates.</p>}
      {students.data && students.data.total_scoped > 0 && students.data.total_matches === 0 && <p className="muted">No students match this search.</p>}
      {students.data && students.data.total_matches > 0 && list.length === 0 && <p>The student list changed. <button className="btn" onClick={students.restart}>Restart student list</button></p>}
      <div className="fields">
        <label>Student
          <select className="input" value={selected?.id ?? ''} disabled={!students.data || list.length === 0} onChange={(e) => {
            const item = list.find((s) => s.id === e.target.value);
            if (!item || item.section_id !== section.id) return;
            reset(); setSelected({ id: item.id, name: item.name, sectionId: item.section_id });
          }}>
            <option value="">Choose a student…</option>
            {pinned && <option value={selected.id}>{selected.name}</option>}
            {list.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label>Tone
          <select className="input" value={toneSel} onChange={(e) => {
            const value = e.target.value;
            if (value === 'warm' || value === 'neutral' || value === 'concerned') { lifecycle.current.revision += 1; clearCopied(); setDraft(null); setGenerationError(null); setTone(value); }
          }}>{TONES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </label>
      </div>
      {selected && <p>Selected: {selected.name}{pinned ? ' (outside these results)' : ''} <button className="btn" onClick={reset}>Clear selection</button></p>}
      <nav aria-label="Student pages" className="row">
        <button className="btn" disabled={!students.data || students.page === 1} onClick={students.previous}>Previous students</button>
        <button className="btn" disabled={!students.data?.next_cursor} onClick={students.next}>Next students</button>
      </nav>
      <ErrorBox error={generationError} />
      <div className="row"><button className="btn primary" disabled={!selected || generation.pending} onClick={generate}>{generation.pending ? 'Drafting…' : draft ? 'Regenerate' : 'Generate draft'}</button></div>
      {draft && <>
        <label>Subject<input className="input" value={draft.subject} onChange={(e) => edit({ ...draft, subject: e.target.value })} /></label>
        <label>Message<textarea className="input" value={draft.body} onChange={(e) => edit({ ...draft, body: e.target.value })} /></label>
        <div className="row"><button className="btn" onClick={copy}>{copied ? 'Copied ✓' : 'Copy'}</button><a className="btn primary" href={mailto}>Open in email</a></div>
        <span className="sr-only" role="status">{copied ? 'Copied to clipboard' : ''}</span>
      </>}
    </section>
  );
}

export default function Reports() {
  // Keep the latch across scope-driven composer remounts until the actual write settles.
  const busy = useRef(false);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const start = useCallback((work: () => Promise<void>) => {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    void work().finally(() => { busy.current = false; if (mounted.current) setPending(false); });
  }, []);
  const section = useActiveSection();
  const { isLoading, ready } = useScope();
  if (!ready) return <><div className="topbar"><h1>Reports</h1><ScopePicker /></div><ScopeStatus /></>;
  if (isLoading) return <Loading />;
  if (!section) return <><div className="topbar"><h1>Reports</h1><ScopePicker /></div><ScopeStatus /><div className="card empty">Create a course and section on the roster first.</div></>;
  return (
    <>
      <div className="topbar">
        <div><h1>Reports</h1><div className="page-sub">{section.name} · class snapshot and parent updates</div></div>
        <div className="row">
          <ScopePicker />
          <a className="btn" href={`/api/reports/sections/${section.id}/gradebook.csv`} download>Download CSV</a>
        </div>
      </div>
      <ScopeStatus />
      <Summary section={section} />
      <ParentComposer key={section.id} section={section} generation={{ pending, start }} />
    </>
  );
}
