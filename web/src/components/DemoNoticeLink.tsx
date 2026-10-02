/** Keep the notice available without leaving an unfinished form or classroom edit. */
export default function DemoNoticeLink() {
  return <footer className="muted" style={{ marginTop: 16, fontSize: '.9rem' }}>
    <a href="/demo-notice" target="_blank" rel="noopener noreferrer">Demo terms and privacy<span className="sr-only"> (opens in a new tab)</span></a>
  </footer>;
}
