import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

const Ctx = createContext({ success() {}, error() {}, dismiss() {} });
export const useToast = () => useContext(Ctx);

/** Transient notifications. Polite live region for success, assertive for errors, so screen readers hear saves. */
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const id = useRef(0);
  const dismiss = useCallback((i) => setItems((l) => l.filter((t) => t.id !== i)), []);
  const push = useCallback((kind, message, ms) => {
    const t = { id: ++id.current, kind, message };
    setItems((l) => [...l.slice(-3), t]);
    if (ms) setTimeout(() => dismiss(t.id), ms);
    return t.id;
  }, [dismiss]);
  const api = useMemo(() => ({
    success: (m) => push('success', m, 3500),
    error: (m) => push('error', m, 8000),
    dismiss,
  }), [push, dismiss]);
  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toasts">
        <div role="status" aria-live="polite">
          {items.filter((t) => t.kind !== 'error').map((t) => <div key={t.id} className="toast">{t.message}</div>)}
        </div>
        <div role="alert">
          {items.filter((t) => t.kind === 'error').map((t) => (
            <div key={t.id} className="toast error"><span>{t.message}</span><button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)}>✕</button></div>
          ))}
        </div>
      </div>
    </Ctx.Provider>
  );
}
