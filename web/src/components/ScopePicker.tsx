import { useScope } from '../scope';

export default function ScopePicker() {
  const { courses, course, section, sections, status, requestedCourseId, requestedSectionId, setCourse, setSection } = useScope();
  const disabled = status === 'pending' || status === 'error';
  const missingCourse = Boolean(requestedCourseId && !course);
  const missingSection = Boolean(requestedSectionId && !section);
  return (
    <div className="scope">
      <select className="input compact" disabled={disabled} value={requestedCourseId ?? ''} onChange={(e) => setCourse(e.target.value)} aria-label="Course">
        <option value="">{status === 'pending' ? 'Loading courses…' : status === 'error' ? 'Courses unavailable' : 'All courses'}</option>
        {missingCourse && <option value={requestedCourseId ?? ''}>{status === 'pending' ? 'Loading saved course…' : status === 'error' ? 'Saved course not loaded' : 'Saved course unavailable'}</option>}
        {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <select className="input compact" disabled={disabled || missingCourse} value={requestedSectionId ?? ''} onChange={(e) => setSection(e.target.value)} aria-label="Section">
        <option value="">{status === 'pending' ? 'Loading sections…' : status === 'error' ? 'Sections unavailable' : 'All sections'}</option>
        {missingSection && <option value={requestedSectionId ?? ''}>{status === 'pending' ? 'Loading saved section…' : status === 'error' ? 'Saved section not loaded' : 'Saved section unavailable'}</option>}
        {sections.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
    </div>
  );
}
