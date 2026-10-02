import { useState } from 'react';
import { BANNER_STORE } from '../api';

const dismissed = () => { try { return sessionStorage.getItem(BANNER_STORE) === '1'; } catch { return false; } };

/** Public-demo notice. Dismissing lasts for the browser session only, so every new visit sees it again. */
export default function DemoBanner() {
  const [hidden, setHidden] = useState(dismissed);
  if (hidden) return null;
  return (
    <div className="demo-banner" role="note">
      <span><strong>Demo app</strong> — synthetic data only. Don&apos;t enter real student information.</span>
      <button type="button" className="btn small" onClick={() => { try { sessionStorage.setItem(BANNER_STORE, '1'); } catch { /* ignore */ } setHidden(true); }} aria-label="Dismiss demo notice">Dismiss</button>
    </div>
  );
}
