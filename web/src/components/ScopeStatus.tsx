import { useScope } from '../scope';
import { ErrorBox, Loading } from './ui';

/** Explain resolution failures without replacing the shell or inventing an All scope. */
export default function ScopeStatus() {
  const { status, error, retry, setCourse, requestedCourseId, course } = useScope();
  if (status === 'pending') return <Loading />;
  if (status === 'missing') return <div className="card empty">
    <p role="alert">Your saved scope is unavailable. {requestedCourseId && !course ? 'Choose a current course to continue.' : 'Choose a current course or section to continue.'}</p>
    <button type="button" className="btn" onClick={() => setCourse(null)}>Use all courses</button>
  </div>;
  if (error) return <div>
    <p role="status">{status === 'ready' ? 'Courses could not refresh. Your last verified scope is still shown.' : 'Could not load courses. Retry to restore your scope.'}</p>
    <ErrorBox error={error} />
    <button type="button" className="btn" onClick={() => retry()}>Retry courses</button>
  </div>;
  return null;
}
