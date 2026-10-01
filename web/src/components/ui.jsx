import { useEffect, useId, useRef } from 'react';
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

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Accessible dialog: labelled, traps Tab, closes on Esc/scrim, and gives focus back to whatever opened it. */
export function Modal({ title, onClose, children, role = 'dialog' }) {
  const box = useRef(null);
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement;
    const el = box.current;
    const items = () => [...el.querySelectorAll(FOCUSABLE)].filter((n) => !n.closest('[hidden]'));
    if (!el.contains(document.activeElement)) (items()[0] ?? el).focus();
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); closeRef.current(); return; }
      if (e.key !== 'Tab') return;
      const list = items();
      if (!list.length) { e.preventDefault(); el.focus(); return; }
      const [first, last] = [list[0], list.at(-1)];
      if (!el.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey, true);
    return () => { document.removeEventListener('keydown', onKey, true); if (opener?.isConnected) opener.focus?.(); };
  }, []);

  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" ref={box} role={role} aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>
  );
}

export const Loading = () => (
  <div className="grid" role="status" aria-busy="true" aria-label="Loading">
    {[60, 90, 75].map((w) => <div key={w} className="skeleton" style={{ width: `${w}%` }} />)}
  </div>
);

export const ErrorBox = ({ error, onRetry }) => error ? (
  <div className="error row" role="alert" style={{ justifyContent: 'space-between' }}>
    <span>{error.message}</span>
    {onRetry && <button type="button" className="btn small" onClick={onRetry}>Retry</button>}
  </div>
) : null;

export const EmptyState = ({ title, children }) => (
  <div className="card empty"><h3>{title}</h3>{children}</div>
);

export function Bar({ value, color }) {
  return <div className="bar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, background: color }} /></div>;
}

export const gradeColor = (pct) => pct == null ? 'var(--muted)' : pct >= 80 ? 'var(--good)' : pct >= 70 ? 'var(--warn)' : 'var(--bad)';
