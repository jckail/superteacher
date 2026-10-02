import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { CourseOut, SectionOut } from './types';
interface Selection { courseId: string | null; sectionId: string | null }
interface ScopeValue {
  courses: CourseOut[]; isLoading: boolean; course: CourseOut | null; section: SectionOut | null;
  sections: SectionOut[]; allSections: (SectionOut & { course: string })[];
  ready: boolean; status: 'pending' | 'error' | 'missing' | 'ready'; error: Error | null;
  requestedCourseId: string | null; requestedSectionId: string | null;
  retry: () => unknown;
  setCourse: (id: string | null) => void; setSection: (id: string | null) => void;
}
const Ctx = createContext<ScopeValue | null>(null);
export function useScope(): ScopeValue {
  const value = useContext(Ctx);
  if (!value) throw new Error('useScope requires ScopeProvider');
  return value;
}
const load = (): Selection => {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem('st-scope') ?? 'null');
    if (saved && typeof saved === 'object') {
      return { courseId: 'courseId' in saved && typeof saved.courseId === 'string' ? saved.courseId : null, sectionId: 'sectionId' in saved && typeof saved.sectionId === 'string' ? saved.sectionId : null };
    }
  } catch { /* Invalid or unavailable storage uses the default scope. */ }
  return { courseId: null, sectionId: null };
};
export function ScopeProvider({ children }: { children: ReactNode }) {
  const metadata = useQuery({ queryKey: ['courses'], queryFn: ({ signal }) => api<CourseOut[]>('/courses', { signal }) });
  const [sel, setSel] = useState<Selection>(load);
  const setCourse = useCallback((courseId: string | null) => setSel({ courseId: courseId || null, sectionId: null }), []);
  const setSection = useCallback((sectionId: string | null) => setSel((p) => ({ ...p, sectionId: sectionId || null })), []);
  const value = useMemo<ScopeValue>(() => {
    const courses = metadata.data ?? [];
    const course = courses.find((c) => c.id === sel.courseId) ?? null;
    const sections = course?.sections ?? courses.flatMap((c) => c.sections);
    const section = sections.find((s) => s.id === sel.sectionId) ?? null;
    // Cached successful metadata remains authoritative during a failed refresh.
    const status = metadata.data === undefined
      ? (metadata.isFetching || metadata.isPending ? 'pending' : 'error')
      : ((sel.courseId && !course) || (sel.sectionId && !section) ? 'missing' : 'ready');
    return {
      courses, isLoading: status === 'pending', course, section, sections,
      allSections: courses.flatMap((c) => c.sections.map((s) => ({ ...s, course: c.name }))),
      ready: status === 'ready', status, error: metadata.error,
      requestedCourseId: sel.courseId, requestedSectionId: sel.sectionId,
      retry: metadata.refetch, setCourse, setSection,
    };
  }, [metadata.data, metadata.error, metadata.isFetching, metadata.isPending, metadata.refetch, sel, setCourse, setSection]);
  useEffect(() => { try { localStorage.setItem('st-scope', JSON.stringify(sel)); } catch { /* private mode */ } }, [sel]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export function useActiveSection(): SectionOut | null {
  const { ready, section, sections } = useScope();
  return ready ? section ?? sections[0] ?? null : null;
}
