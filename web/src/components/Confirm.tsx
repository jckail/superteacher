import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Modal } from './ui';

export interface ConfirmOptions { title?: string; message?: ReactNode; confirmLabel?: string; cancelLabel?: string; danger?: boolean }
type Confirm = (options: ConfirmOptions) => Promise<boolean>;
const Ctx = createContext<Confirm | null>(null);

/** `const confirm = useConfirm(); if (await confirm({ title, message, confirmLabel })) …` — replaces window.confirm. */
export function useConfirm(): Confirm { const value = useContext(Ctx); if (!value) throw new Error('useConfirm requires ConfirmProvider'); return value; }

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const descriptionId = useId();
  const [req, setReq] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback<Confirm>((opts) => new Promise<boolean>((resolve) => { resolver.current?.(false); resolver.current = resolve; setReq(opts); }), []);
  useEffect(() => () => { resolver.current?.(false); resolver.current = null; }, []);
  const settle = (v: boolean) => { resolver.current?.(v); resolver.current = null; setReq(null); };
  return (
    <Ctx.Provider value={confirm}>
      {children}
      {req && (
        <Modal title={req.title ?? 'Are you sure?'} role="alertdialog" descriptionId={req.message ? descriptionId : undefined} onClose={() => settle(false)}>
          {req.message && <p id={descriptionId} style={{ margin: 0 }}>{req.message}</p>}
          <div className="confirm-actions">
            <button type="button" className="btn" autoFocus onClick={() => settle(false)}>{req.cancelLabel ?? 'Cancel'}</button>
            <button type="button" className={`btn ${req.danger ? 'danger-solid' : 'primary'}`} onClick={() => settle(true)}>{req.confirmLabel ?? 'Confirm'}</button>
          </div>
        </Modal>
      )}
    </Ctx.Provider>
  );
}
