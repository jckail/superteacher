import { createContext, useCallback, useContext, useRef, useState } from 'react';
import { Modal } from './ui';

const Ctx = createContext(null);

/** `const confirm = useConfirm(); if (await confirm({ title, message, confirmLabel })) …` — replaces window.confirm. */
export const useConfirm = () => useContext(Ctx);

export function ConfirmProvider({ children }) {
  const [req, setReq] = useState(null);
  const resolver = useRef(null);
  const confirm = useCallback((opts) => new Promise((resolve) => { resolver.current = resolve; setReq(opts); }), []);
  const settle = (v) => { resolver.current?.(v); resolver.current = null; setReq(null); };
  return (
    <Ctx.Provider value={confirm}>
      {children}
      {req && (
        <Modal title={req.title ?? 'Are you sure?'} role="alertdialog" onClose={() => settle(false)}>
          {req.message && <p style={{ margin: 0 }}>{req.message}</p>}
          <div className="confirm-actions">
            <button type="button" className="btn" autoFocus onClick={() => settle(false)}>{req.cancelLabel ?? 'Cancel'}</button>
            <button type="button" className={`btn ${req.danger ? 'danger-solid' : 'primary'}`} onClick={() => settle(true)}>{req.confirmLabel ?? 'Confirm'}</button>
          </div>
        </Modal>
      )}
    </Ctx.Provider>
  );
}
