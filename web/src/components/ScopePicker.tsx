import { useScope } from '../scope';

export default function ScopePicker() {
  const { courses, course, section, sections, setCourse, setSection } = useScope();
  return (
    <div className="scope">
      <select className="input compact" value={course?.id ?? ''} onChange={(e) => setCourse(e.target.value)} aria-label="Course">
        <option value="">All courses</option>
        {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <select className="input compact" value={section?.id ?? ''} onChange={(e) => setSection(e.target.value)} aria-label="Section">
        <option value="">All sections</option>
        {sections.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
    </div>
  );
}
