import { useEffect, useId, useRef, useState } from 'react';
import { api, downloadFile } from '../api';
import { useAuth } from '../auth';
import { Modal } from './ui';
import { useToast } from './Toast';

/** Accounts mode: who is signed in, plus sign out, sign out everywhere, export, and delete. */
export default function AccountMenu() {
  const { email, logout, logoutAll } = useAuth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const root = useRef(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (!root.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') { setOpen(false); root.current?.querySelector('button')?.focus(); } };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const exportData = async () => {
    setOpen(false);
    try { await downloadFile('/account/export', 'super-teacher-export.json'); toast.success('Export downloaded'); }
    catch (e) { toast.error(e.message || 'Export failed'); }
  };

  return (
    <div className="account-menu" ref={root}>
      <button type="button" className="btn side-extra account-btn" aria-expanded={open} aria-controls={menuId} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden>👤</span> <span className="account-email" title={email}>{email}</span>
      </button>
      {open && (
        <div className="account-pop card" id={menuId} role="group" aria-label="Account">
          <p className="muted account-who">Signed in as <strong>{email}</strong></p>
          <button type="button" className="btn" onClick={logout}>Sign out</button>
          <button type="button" className="btn" onClick={logoutAll}>Sign out everywhere</button>
          <button type="button" className="btn" onClick={exportData}>Export my data</button>
          <button type="button" className="btn danger" onClick={() => { setOpen(false); setDeleting(true); }}>Delete account…</button>
        </div>
      )}
      {deleting && <DeleteAccount email={email} onClose={() => setDeleting(false)} />}
    </div>
  );
}

function DeleteAccount({ email, onClose }) {
  const { accountDeleted } = useAuth();
  const [typed, setTyped] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const ok = typed.trim().toLowerCase() === email.toLowerCase();

  const submit = async (e) => {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      await api('/account', { method: 'DELETE', body: { email: typed.trim() } });
      accountDeleted();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Delete your account?" role="alertdialog" onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
        <p style={{ margin: 0 }}>
          This permanently deletes your account and <strong>everything in it</strong>: courses, students, grades, attendance and notes.
          It can&apos;t be undone. Consider exporting your data first.
        </p>
        <label style={{ display: 'grid', gap: 6 }}>
          Type <strong>{email}</strong> to confirm
          <input className="input" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </label>
        <div role="alert">{error && <span className="error">{error}</span>}</div>
        <div className="confirm-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn danger-solid" disabled={!ok || busy}>{busy ? 'Deleting…' : 'Delete everything'}</button>
        </div>
      </form>
    </Modal>
  );
}
