import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';

const Ctx = createContext(null);
export const useScope = () => useContext(Ctx);

const load = () => { try { return JSON.parse(localStorage.getItem('st-scope')) ?? {}; } catch { return {}; } };

/** Which course/section the teacher is looking at. Persisted; validated against live data. */
export function ScopeProvider({ children }) {
  const { data: courses = [], isLoading } = useQuery({ queryKey: ['courses'], queryFn: () => api('/courses') });
  const [sel, setSel] = useState(load);

  const value = useMemo(() => {
    const course = courses.find((c) => c.id === sel.courseId) ?? null;
    const sections = (course ?? { sections: courses.flatMap((c) => c.sections) }).sections;
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

/** Gradebook/attendance need exactly one section: fall back to the first available. */
export function useActiveSection() {
  const { section, sections, allSections } = useScope();
  return section ?? sections[0] ?? allSections[0] ?? null;
}
