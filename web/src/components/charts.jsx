import { useState } from 'react';
import { gradeColor } from './ui';

/** Score-over-time line chart with labelled axes; points are focusable and show their detail below. */
export function TrendChart({ points }) {
  const [active, setActive] = useState(null);
  const pts = points.filter((p) => p.pct != null);
  if (pts.length < 2) return <p className="muted">Not enough graded work to chart yet.</p>;
  const W = 420, H = 190, L = 34, R = 12, T = 12, B = 28;
  const lo = Math.min(60, Math.floor(Math.min(...pts.map((p) => p.pct)) / 10) * 10);
  const hi = 100;
  const x = (i) => L + (i / (pts.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (H - T - B);
  const ticks = [];
  for (let t = lo; t <= hi; t += (hi - lo) > 40 ? 20 : 10) ticks.push(t);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.pct).toFixed(1)}`).join(' ');
  const cur = pts[active ?? pts.length - 1];
  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`Score trend across ${pts.length} assignments, latest ${Math.round(pts.at(-1).pct)}%`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid-line" x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
            <text x={L - 6} y={y(t) + 4} textAnchor="end">{t}%</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(70)} y2={y(70)} stroke="var(--warn)" strokeDasharray="4 4" opacity=".6" />
        <path d={d} fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {pts.map((p, i) => (
          <circle key={i} className="pt" cx={x(i)} cy={y(p.pct)} r={active === i ? 6 : 4.5} fill={gradeColor(p.pct)} stroke="var(--surface)" strokeWidth="1.5"
            tabIndex={0} role="img" aria-label={`${p.label}: ${Math.round(p.pct)}%${p.detail ? `, ${p.detail}` : ''}`}
            onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} />
        ))}
        <text x={L} y={H - 8} textAnchor="start">{pts[0].short}</text>
        <text x={W - R} y={H - 8} textAnchor="end">{pts.at(-1).short}</text>
      </svg>
      <figcaption className="chart-tip"><strong>{cur.label}</strong> · <span style={{ color: gradeColor(cur.pct) }}>{Math.round(cur.pct)}%</span>{cur.detail && <span className="muted"> · {cur.detail}</span>} <span className="muted-sm">(dashed line = 70%)</span></figcaption>
    </figure>
  );
}

export const BANDS = [['A', 'var(--good)'], ['B', '#5bb98c'], ['C', '#e8a33d'], ['D', '#e0703c'], ['F', 'var(--bad)']];

/** Grade distribution as bars, with a screen-reader table carrying the same numbers. */
export function Distribution({ dist }) {
  const max = Math.max(1, ...BANDS.map(([b]) => dist[b] ?? 0));
  const total = BANDS.reduce((n, [b]) => n + (dist[b] ?? 0), 0);
  return (
    <figure style={{ margin: 0 }}>
      <div className="dist" aria-hidden="true">
        {BANDS.map(([b, color]) => (
          <div key={b} className="col">
            <div className="num" style={{ fontWeight: 600 }}>{dist[b] ?? 0}</div>
            <div className="bar-fill" style={{ height: Math.max(4, ((dist[b] ?? 0) / max) * 110), background: color }} />
            <div className="muted">{b}</div>
          </div>
        ))}
      </div>
      <table className="sr-only">
        <caption>Grade distribution</caption>
        <thead><tr><th>Letter</th><th>Students</th></tr></thead>
        <tbody>{BANDS.map(([b]) => <tr key={b}><td>{b}</td><td>{dist[b] ?? 0}</td></tr>)}</tbody>
      </table>
      <figcaption className="muted-sm" style={{ marginTop: 6 }}>{total} graded {total === 1 ? 'student' : 'students'}</figcaption>
    </figure>
  );
}

const DAY_LABELS = ['M', 'T', 'W', 'T', 'F'];
const parse = (s) => new Date(`${s}T00:00:00`);

/** Attendance as a week-by-week calendar: one column per week, Mon–Fri down. */
export function AttendanceHeat({ days }) {
  if (!days.length) return <p className="muted">No attendance recorded yet.</p>;
  const cols = [];
  let weekKey = null;
  for (const a of days) {
    const d = parse(a.day);
    const dow = (d.getDay() + 6) % 7;     // Mon = 0
    if (dow > 4) continue;
    const monday = new Date(d); monday.setDate(d.getDate() - dow);
    const k = monday.toISOString().slice(0, 10);
    if (k !== weekKey) { cols.push(Array(5).fill(null)); weekKey = k; }
    cols.at(-1)[dow] = a;
  }
  const counts = days.reduce((m, a) => ({ ...m, [a.status]: (m[a.status] ?? 0) + 1 }), {});
  const summary = Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(', ');
  return (
    <div>
      <div className="heat-wrap" role="img" aria-label={`Attendance over the last ${days.length} school days: ${summary}`}>
        <div className="heat-days" aria-hidden="true">{DAY_LABELS.map((l, i) => <span key={i}>{l}</span>)}</div>
        <div className="heat" aria-hidden="true">
          {cols.flatMap((c, ci) => c.map((a, ri) => <i key={`${ci}-${ri}`} className={a?.status ?? ''} title={a ? `${a.day}: ${a.status}` : undefined} />))}
        </div>
      </div>
      <div className="legend">
        {[['present', 'var(--good)'], ['tardy', '#e8a33d'], ['absent', 'var(--bad)'], ['excused', 'var(--muted)']].map(([k, c]) => <span key={k}><i style={{ background: c }} />{k}</span>)}
      </div>
    </div>
  );
}
