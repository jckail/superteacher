import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import type { ReactNode } from 'react';
interface ToastApi { success: (message: string) => number; error: (message: string) => number; dismiss: (id: number) => void }
interface ToastItem { id: number; kind: 'success' | 'error'; message: string }
const Ctx = createContext<ToastApi>({ success: () => 0, error: () => 0, dismiss: () => {} });
export const useToast = () => useContext(Ctx);

/** Transient notifications. Polite live region for success, assertive for errors, so screen readers hear saves. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const id = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  useEffect(() => { const activeTimers = timers.current; return () => { activeTimers.forEach(clearTimeout); activeTimers.clear(); }; }, []);
  const dismiss = useCallback((i: number) => { clearTimeout(timers.current.get(i)); timers.current.delete(i); setItems((l) => l.filter((t) => t.id !== i)); }, []);
  const push = useCallback((kind: ToastItem['kind'], message: string, ms: number) => {
    const t: ToastItem = { id: ++id.current, kind, message };
    setItems((list) => {
      list.slice(0, Math.max(0, list.length - 3)).forEach((item) => { clearTimeout(timers.current.get(item.id)); timers.current.delete(item.id); });
      return [...list.slice(-3), t];
    });
    if (ms) timers.current.set(t.id, setTimeout(() => dismiss(t.id), ms));
    return t.id;
  }, [dismiss]);
  const api = useMemo<ToastApi>(() => ({
    success: (m: string) => push('success', m, 3500),
    error: (m: string) => push('error', m, 0),
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
            <div key={t.id} className="toast error"><span>{t.message}</span><button type="button" aria-label={`Dismiss notification: ${t.message}`} onClick={() => dismiss(t.id)}>✕</button></div>
          ))}
        </div>
      </div>
    </Ctx.Provider>
  );
}
