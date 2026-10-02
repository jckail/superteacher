import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { CourseOut, SectionOut } from './types';
interface Selection { courseId: string | null; sectionId: string | null }
interface ScopeValue {
  courses: CourseOut[]; isLoading: boolean; course: CourseOut | null; section: SectionOut | null;
  sections: SectionOut[]; allSections: (SectionOut & { course: string })[];
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
  const { data: courses = [], isLoading } = useQuery({ queryKey: ['courses'], queryFn: ({ signal }) => api<CourseOut[]>('/courses', { signal }) });
  const [sel, setSel] = useState<Selection>(load);
  const value = useMemo<ScopeValue>(() => {
    const course = courses.find((c) => c.id === sel.courseId) ?? null;
    const sections = course?.sections ?? courses.flatMap((c) => c.sections);
    const section = sections.find((s) => s.id === sel.sectionId) ?? null;
    return {
      courses, isLoading, course, section, sections,
      allSections: courses.flatMap((c) => c.sections.map((s) => ({ ...s, course: c.name }))),
      setCourse: (courseId) => setSel({ courseId: courseId || null, sectionId: null }),
      setSection: (sectionId) => setSel((p) => ({ ...p, sectionId: sectionId || null })),
    };
  }, [courses, isLoading, sel]);
  useEffect(() => { try { localStorage.setItem('st-scope', JSON.stringify(sel)); } catch { /* private mode */ } }, [sel]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export function useActiveSection(): SectionOut | null {
  const { section, sections, allSections } = useScope();
  return section ?? sections[0] ?? allSections[0] ?? null;
}
