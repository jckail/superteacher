import { useEffect } from 'react';
import { RISK_LABEL } from '../api';

export const RiskChip = ({ risk }) => <span className={`chip ${risk}`}>{RISK_LABEL[risk]}</span>;

export function Stat({ label, value, hint }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

export const Loading = () => (
  <div className="grid" aria-busy="true">
    {[60, 90, 75].map((w) => <div key={w} className="skeleton" style={{ width: `${w}%` }} />)}
  </div>
);

export const ErrorBox = ({ error }) => error ? <div className="error" role="alert">{error.message}</div> : null;

export function Bar({ value, color }) {
  return <div className="bar"><i style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, background: color }} /></div>;
}

/** Tiny inline trend line over 0-100 percentages. */
export function Sparkline({ values, width = 220, height = 48 }) {
  const pts = values.filter((v) => v != null);
  if (pts.length < 2) return <span className="muted">Not enough data</span>;
  const x = (i) => (i / (pts.length - 1)) * (width - 8) + 4;
  const y = (v) => height - 4 - (Math.max(40, Math.min(100, v)) - 40) / 60 * (height - 8);
  const d = pts.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return (
    <svg width={width} height={height} role="img" aria-label={`Score trend, latest ${Math.round(pts.at(-1))}%`}>
      <path d={d} fill="none" stroke="var(--brand)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(pts.length - 1)} cy={y(pts.at(-1))} r="4" fill="var(--brand)" />
    </svg>
  );
}

export const gradeColor = (pct) => pct == null ? 'var(--muted)' : pct >= 80 ? 'var(--good)' : pct >= 70 ? 'var(--warn)' : 'var(--bad)';
