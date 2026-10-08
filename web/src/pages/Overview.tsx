import type { Overview as OverviewData } from '../types';
import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api';
import { useScope } from '../scope';
import { useSchoolCalendar } from '../schoolCalendar';
import ScopePicker from '../components/ScopePicker';
import ScopeStatus from '../components/ScopeStatus';
import { ActivityRings, Distribution } from '../components/charts';
import { EmptyState, ErrorBox, Loading, RiskChip, Stat, gradeColor } from '../components/ui';

export default function Overview() {
  const { course, section, ready } = useScope();
  const q = useQuery({
    enabled: ready,
    queryKey: ['overview', course?.id, section?.id],
    queryFn: ({ signal }) => api<OverviewData>(`/overview?${new URLSearchParams({ ...(course && { course_id: course.id }), ...(section && { section_id: section.id }) })}`, { signal }),
  });
  const o = ready ? q.data : undefined;
  const qc = useQueryClient();
  const calendar = useSchoolCalendar(ready);
  const courseId = course?.id;
  const sectionId = section?.id;
  const identity = JSON.stringify([ready, courseId, sectionId]);
  const attempt = useRef({ identity, day: null as string | null });
  if (attempt.current.identity !== identity) attempt.current = { identity, day: null };
  const schoolDay = calendar.data?.today;
  const cutoff = o?.as_of;
  const fetching = q.isFetching;
  const readError = q.error;
  useEffect(() => {
    if (!ready || !schoolDay || !cutoff || cutoff >= schoolDay || fetching || readError) return;
    if (attempt.current.day === schoolDay) return;
    // Mark before invalidation so an older response cannot cause a same-day loop.
    attempt.current.day = schoolDay;
    void qc.invalidateQueries({ queryKey: ['overview', courseId, sectionId], exact: true });
  }, [ready, identity, courseId, sectionId, schoolDay, cutoff, fetching, readError, qc]);
  const hour = new Date().getHours();
  return (
    <>
      <div className="topbar">
        <div>
          <h1>{hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'}</h1>
          <div className="page-sub">{o ? (o.students === 0 ? 'Build your classroom to get started.' : o.at_risk + o.watch ? `${o.at_risk + o.watch} students could use your attention.` : o.unknown ? `${o.unknown} student${o.unknown === 1 ? '' : 's'} need${o.unknown === 1 ? 's' : ''} more data to assess progress.` : 'Everyone is on track.') : 'Loading your classroom…'}</div>
        </div>
        <ScopePicker />
      </div>
      <ScopeStatus />
      {ready && calendar.error && <div>
        <ErrorBox error={calendar.error} />
        <button className="btn" disabled={calendar.isFetching} onClick={() => void calendar.refetch()}>Retry school calendar</button>
      </div>}
      {o && <p className="as-of">Progress calculated through {o.as_of}</p>}
      {ready && cutoff && schoolDay && cutoff < schoolDay && <p role="status">
        Progress is shown through {cutoff}. {fetching ? 'Updating school-day calculations…' : readError ? 'Refresh failed. Use Retry to update progress.' : 'Newer school-day calculations are available.'}
        {!fetching && !readError && <> <button className="btn small" onClick={() => void q.refetch()}>Refresh progress</button></>}
      </p>}
      <ErrorBox error={ready ? q.error : null} onRetry={() => q.refetch()} />
      {ready && q.isLoading && <Loading />}
      {o && (o.students === 0 ? (
        <EmptyState title="No students yet">
          <p>Add your first student or import a class to see who needs you today.</p>
          <div className="row"><Link className="btn primary" to="/roster">Go to roster</Link></div>
        </EmptyState>
      ) : (
        <>
          <div className="grid today">
            <section className="card rings-card" aria-label="Class progress">
              <ActivityRings rings={[
                { label: 'Showing up', value: o.attendance_rate, color: 'var(--ring-attendance)' },
                { label: 'Work handed in', value: o.homework_rate, color: 'var(--ring-homework)' },
                { label: 'Overall grade', value: o.average, color: 'var(--ring-average)' },
              ]} />
              <ul className="rings-legend">
                {[
                  ['var(--ring-attendance)', 'Showing up', o.attendance_rate, 'of class time attended'],
                  ['var(--ring-homework)', 'Work handed in', o.homework_rate, 'of assigned work'],
                  ['var(--ring-average)', 'Overall grade', o.average, 'weighted across all work'],
                ].map(([color, label, value, note]) => (
                  <li key={label as string}><i style={{ background: color as string }} aria-hidden="true" /><b>{label as string}</b><span>{value == null ? 'No data yet' : `${Math.round(value as number)}% ${note as string}`}</span></li>
                ))}
              </ul>
            </section>
            <section className="card">
              <h2>Needs your attention</h2>
              {o.unknown > 0 && <p className="muted">{o.unknown} student{o.unknown === 1 ? '' : 's'} lack{o.unknown === 1 ? 's' : ''} enough data to assess progress. <Link to="/roster?status=unknown">Review records needing data</Link>.</p>}
              {o.attention.length === 0 ? <p className="muted">{o.unknown === o.students ? 'Record work or attendance before assessing progress.' : o.unknown ? 'No attention flags among students with evidence.' : 'Nobody is flagged. 🎉'}</p> : (
                <ul className="attention">
                  {o.attention.map((s) => (
                    <li key={s.id}>
                      <Link to={`/students/${s.id}`}>
                        <span className="row" style={{ justifyContent: 'space-between' }}>
                          <strong>{s.name}</strong>
                          <span className="row"><span className="num" style={{ color: gradeColor(s.average) }}>{fmt(s.average, '%')}</span><RiskChip risk={s.risk} /></span>
                        </span>
                        <span className="why">{s.course} · {s.section} — {s.risk_reasons.join(' · ')}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <div className="grid stats">
            <Stat label="Students" value={o.students} />
            <Stat label="Class average" value={fmt(o.average, '%')} hint={o.average != null && `Weighted across tests, quizzes, homework`} />
            <Stat label="Attendance" value={fmt(o.attendance_rate, '%')} hint="Excused absences excluded" />
            <Stat label="Homework in" value={fmt(o.homework_rate, '%')} />
            <Stat label="At risk" value={o.at_risk} hint={`${o.watch} more on watch`} />
            <Stat label="Not enough data" value={o.unknown} hint="Work or attendance evidence needed" />
          </div>
          <section className="card">
            <h2 id="dist-h">Grade distribution</h2>
            <Distribution dist={o.distribution} />
          </section>
        </>
      ))}
    </>
  );
}
