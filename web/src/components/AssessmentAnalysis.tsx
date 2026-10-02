import { useId } from 'react';
import type { AssessmentStat } from '../types';

const tieBreak = (a: AssessmentStat, b: AssessmentStat) => a.title.localeCompare(b.title) || a.id.localeCompare(b.id);
const percentage = (value: number) => `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}%`;

/** Review aggregate assignment evidence without inferring individual mistakes. */
export default function AssessmentAnalysis({ rows, asOf, students }: {
  rows: AssessmentStat[]; asOf: string; students: number;
}) {
  const id = useId();
  const graded = rows.filter((row): row is AssessmentStat & { average: number } =>
    row.graded > 0 && row.average != null && Number.isFinite(row.average))
    .sort((a, b) => a.average - b.average || tieBreak(a, b)).slice(0, 5);
  const missing = rows.filter((row): row is AssessmentStat & { missing_pct: number } =>
    students > 0 && row.due_date <= asOf && row.missing_pct != null && Number.isFinite(row.missing_pct) && row.missing_pct > 0)
    .sort((a, b) => b.missing_pct - a.missing_pct || tieBreak(a, b)).slice(0, 5);
  return (
    <section className="card" aria-labelledby={`${id}-review`}>
      <h2 id={`${id}-review`}>Assessment review</h2>
      <p className="muted">Compare recorded scores and missing work before choosing what to review. These are assignment totals, not question-level mistakes.</p>
      <section aria-labelledby={`${id}-graded`}>
        <h3 id={`${id}-graded`}>Lowest graded averages</h3>
        <p className="muted">Up to five assignments, lowest average first. Averages include recorded scores only; missing scores are not counted as zero.</p>
        {!graded.length ? <p className="muted">No graded averages to compare yet.</p> : <ol>
          {graded.map((row) => <li key={row.id}>
            <strong>{row.title}</strong>: <span className="num">{percentage(row.average)}</span> average
            <div className="muted">{row.graded} scored of {students} students · Due <time dateTime={row.due_date}>{row.due_date}</time></div>
          </li>)}
        </ol>}
      </section>
      <section aria-labelledby={`${id}-missing`}>
        <h3 id={`${id}-missing`}>Most missing work</h3>
        <p className="muted">Up to five due assignments, highest missing percentage first. Missing work counts students without a recorded score once an assignment is due, through <time dateTime={asOf}>{asOf}</time>.</p>
        {!missing.length ? <p className="muted">No missing scores reported on due assignments. Future assignments are not counted as missing.</p> : <ol>
          {missing.map((row) => <li key={row.id}>
            <strong>{row.title}</strong>: <span className="num">{percentage(row.missing_pct)}</span> missing
            <div className="muted">{row.graded} scored of {students} students · Due <time dateTime={row.due_date}>{row.due_date}</time></div>
          </li>)}
        </ol>}
      </section>
    </section>
  );
}
