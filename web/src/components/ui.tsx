import { useEffect, useId, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { ReactNode, RefObject } from 'react';
import type { Risk } from '../types';
import { RISK_LABEL } from '../api';

export const RiskChip = ({ risk }: { risk: Risk }) => <span className={`chip ${risk}`}>{RISK_LABEL[risk]}</span>;

export function Stat({ label, value, hint }: { label: ReactNode; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const focusableItems = (el: HTMLElement) => [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((node) =>
  !node.matches(':disabled') && !node.closest('[hidden], [inert], [aria-hidden="true"]') && getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden');

const dialogStack: HTMLElement[] = [];
const isolatedNodes = new WeakMap<HTMLElement, { count: number; original: boolean }>();
let originalOverflow = '';

function isolate(node: HTMLElement) {
  const state = isolatedNodes.get(node) ?? { count: 0, original: Boolean(node.inert) };
  state.count += 1;
  isolatedNodes.set(node, state);
  node.inert = true;
}

function release(node: HTMLElement) {
  const state = isolatedNodes.get(node);
  if (!state) return;
  state.count -= 1;
  if (state.count === 0) { node.inert = state.original; isolatedNodes.delete(node); }
}

function restoreFocusAfterClose(ref: RefObject<HTMLElement>, opener: Element | null) {
  if (!ref.current && opener instanceof HTMLElement && opener.isConnected) opener.focus();
}

/** Focus and background isolation shared by dialogs and the assistant's mobile overlay. */
export function useDialogFocus(ref: RefObject<HTMLElement>, onClose: () => void, modal = true, initialFocus?: RefObject<HTMLElement>) {
  // Capture before a descendant's autoFocus runs during commit.
  const opener = useRef(document.activeElement);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useLayoutEffect(() => {
    const previousFocus = opener.current;
    const el = ref.current;
    if (el && !el.contains(document.activeElement)) (initialFocus?.current ?? focusableItems(el)[0] ?? el).focus();
    return () => restoreFocusAfterClose(ref, previousFocus);
  }, [ref, initialFocus, modal]);
  useEffect(() => {
    const previousFocus = opener.current;
    const el = ref.current;
    if (!el || !modal) return;
    if (!dialogStack.length) originalOverflow = document.body.style.overflow;
    dialogStack.push(el);
    if (!el.contains(document.activeElement)) (initialFocus?.current ?? focusableItems(el)[0] ?? el).focus();
    const isolated: HTMLElement[] = [];
    let branch: HTMLElement = el;
    while (branch.parentElement && branch !== document.body) {
      for (const sibling of branch.parentElement.children) {
        if (sibling instanceof HTMLElement && sibling !== branch && !['SCRIPT', 'STYLE'].includes(sibling.tagName)) {
          isolated.push(sibling);
          isolate(sibling);
        }
      }
      branch = branch.parentElement;
    }
    document.body.style.overflow = 'hidden';
    const items = () => focusableItems(el);
    const isTop = () => dialogStack.at(-1) === el;
    const onKey = (event: KeyboardEvent) => {
      if (!isTop()) return;
      if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); closeRef.current(); return; }
      if (event.key !== 'Tab') return;
      const list = items();
      if (!list.length) { event.preventDefault(); el.focus(); return; }
      const first = list[0], last = list[list.length - 1];
      if (!el.contains(document.activeElement) || document.activeElement === el) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    const onFocus = (event: FocusEvent) => {
      if (isTop() && event.target instanceof Node && !el.contains(event.target)) (items()[0] ?? el).focus();
    };
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('focusin', onFocus);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('focusin', onFocus);
      dialogStack.splice(dialogStack.indexOf(el), 1);
      isolated.forEach(release);
      if (!dialogStack.length) document.body.style.overflow = originalOverflow;
      restoreFocusAfterClose(ref, previousFocus);
    };
  }, [ref, modal, initialFocus]);
}

/** Accessible dialog: labelled, isolates background, traps focus and restores the opener. */
export function Modal({ title, onClose, children, role = 'dialog', descriptionId }: { title: string; onClose: () => void; children: ReactNode; role?: 'dialog' | 'alertdialog'; descriptionId?: string }) {
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useDialogFocus(box, onClose);
  return createPortal(
    <div className="scrim" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal" ref={box} role={role} aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} tabIndex={-1}>
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>, document.body,
  );
}

export const Loading = () => (
  <div className="grid" role="status" aria-busy="true" aria-label="Loading">
    <span className="sr-only">Loading…</span>
    {[60, 90, 75].map((w) => <div key={w} aria-hidden="true" className="skeleton" style={{ width: `${w}%` }} />)}
  </div>
);

export const ErrorBox = ({ error, onRetry }: { error?: Error | null; onRetry?: () => unknown }) => error ? (
  <div className="error row" role="alert" style={{ justifyContent: 'space-between' }}>
    <span>{error.message}</span>
    {onRetry && <button type="button" className="btn small" onClick={onRetry}>Retry</button>}
  </div>
) : null;

export const EmptyState = ({ title, children }: { title: string; children?: ReactNode }) => (
  <div className="card empty"><h2>{title}</h2>{children}</div>
);

export function Bar({ value, color }: { value?: number | null; color?: string }) {
  return <div className="bar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, background: color }} /></div>;
}

export const gradeColor = (pct: number | null | undefined) => pct == null ? 'var(--muted)' : pct >= 80 ? 'var(--good)' : pct >= 70 ? 'var(--warn)' : 'var(--bad)';
