import { useEffect, useRef } from 'react';

/** Public explanation of the demo's rules and current data flows; no private requests. */
export default function DemoNotice() {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const previous = document.title;
    document.title = 'Demo terms and privacy · Super Teacher';
    heading.current?.focus();
    return () => { document.title = previous; };
  }, []);

  return <main className="login-wrap">
    <article className="card" style={{ width: 'min(760px, 100%)', padding: 28, overflowWrap: 'anywhere' }}>
      <h1 ref={heading} tabIndex={-1}>Demo terms and privacy</h1>
      <p>This notice describes the Super Teacher demo. Updated October 2, 2026.</p>
      <h2>Use synthetic data only</h2>
      <p>Try the workspace with fictional students and classroom records. Do not enter real student information, confidential school records, passwords or other secrets. Your own email address may be used to sign in when email accounts are enabled.</p>
      <p>Review grades, insights and parent drafts before using them. AI output can be wrong. This demo is not an official gradebook or a channel for sending parent messages. School or real-roster use needs separate approval and privacy review before any real records are entered.</p>
      <h2>What is stored</h2>
      <p>The application database stores classroom records you save: courses, sections, student profiles, assessments, scores, attendance, notes and cached AI insights. Email accounts also store your email address, sign-in and session records, and usage counters. A shared passcode workspace is shared by everyone with that passcode.</p>
      <p>Your browser uses a session cookie for sign-in. It also keeps preferences and recent chat messages; chat history can survive a reload in the same tab. Sign out on shared computers. Downloads and text you copy remain on your device until you remove them.</p>
      <h2>What goes to AI</h2>
      <p>When AI is configured and you use chat, insights or parent-draft generation, the application sends requests to Anthropic. These can include your messages and relevant classroom names, grades, attendance, assignment details and teacher notes. Chat and insights can include notes; parent-draft requests exclude stored teacher notes.</p>
      <p>Without an AI provider key, insights and parent drafts can use local rules or templates, and chat reports that AI is unavailable. Review <a href="https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data" target="_blank" rel="noopener noreferrer">Anthropic’s API data-retention information<span className="sr-only"> (opens in a new tab)</span></a>. This demo does not promise zero provider retention.</p>
      <h2>Hosting and sign-in email</h2>
      <p>The Cloud Run deployment uses Google Cloud for hosting and replica storage. When email sign-in is enabled, your address and a one-time sign-in link are sent through the configured email provider, such as SendGrid or an SMTP service. Hosting and provider logs may retain request metadata. Do not share sign-in links or include private records in support reports.</p>
      <h2>Export and deletion</h2>
      <p>In email accounts mode, open your account menu and choose <strong>Export my data</strong> to download your classroom data as JSON. Choose <strong>Delete account…</strong> and type your email address to delete the account and its classroom records from the active database. Export first if you want a copy; account deletion cannot be undone in the app.</p>
      <p>In shared passcode mode there is no personal account menu. Reports provides CSV exports; ask the workspace operator about removal of shared data. Deleting active data does not immediately remove earlier backups, replica history, provider records, or copies you downloaded. This demo does not offer an automatic data-expiry schedule or a guaranteed backup-deletion date.</p>
      <p><a className="btn" href="/">Back to Super Teacher</a></p>
    </article>
  </main>;
}
