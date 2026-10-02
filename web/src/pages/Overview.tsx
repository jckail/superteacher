import type { Overview as OverviewData } from '../types';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, fmt } from '../api';
import { useScope } from '../scope';
import ScopePicker from '../components/ScopePicker';
import { Distribution } from '../components/charts';
import { EmptyState, ErrorBox, Loading, RiskChip, Stat, gradeColor } from '../components/ui';

export default function Overview() {
  const { course, section } = useScope();
  const q = useQuery({
    queryKey: ['overview', course?.id, section?.id],
    queryFn: ({ signal }) => api<OverviewData>(`/overview?${new URLSearchParams({ ...(course && { course_id: course.id }), ...(section && { section_id: section.id }) })}`, { signal }),
  });
  const o = q.data;
  const hour = new Date().getHours();
  return (
    <>
      <div className="topbar">
        <div>
          <h1>{hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'} 👋</h1>
          <div className="page-sub">{o ? (o.students === 0 ? 'Build your classroom to get started.' : o.at_risk + o.watch ? `${o.at_risk + o.watch} students could use your attention.` : o.unknown ? `${o.unknown} student${o.unknown === 1 ? '' : 's'} need${o.unknown === 1 ? 's' : ''} more data to assess progress.` : 'Everyone is on track.') : 'Loading your classroom…'}</div>
        </div>
        <ScopePicker />
      </div>
      <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      {q.isLoading && <Loading />}
      {o && (o.students === 0 ? (
        <EmptyState title="No students yet">
          <p>Add your first student or import a class to see who needs you today.</p>
          <div className="row"><Link className="btn primary" to="/roster">Go to roster</Link></div>
        </EmptyState>
      ) : (
        <>
          <div className="grid stats">
            <Stat label="Students" value={o.students} />
            <Stat label="Class average" value={fmt(o.average, '%')} hint={o.average != null && `Weighted across tests, quizzes, homework`} />
            <Stat label="Attendance" value={fmt(o.attendance_rate, '%')} hint="Excused absences excluded" />
            <Stat label="Homework in" value={fmt(o.homework_rate, '%')} />
            <Stat label="At risk" value={o.at_risk} hint={`${o.watch} more on watch`} />
            <Stat label="Not enough data" value={o.unknown} hint="Work or attendance evidence needed" />
          </div>
          <div className="grid two">
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
            <section className="card">
              <h2 id="dist-h">Grade distribution</h2>
              <Distribution dist={o.distribution} />
            </section>
          </div>
        </>
      ))}
    </>
  );
}
