import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from './api';
import type { Risk, RosterDirection, RosterSort, StudentPage } from './types';

interface Filters {
  courseId?: string; sectionId?: string; search: string; risk: Risk | '';
  sort: RosterSort; direction: RosterDirection;
}
let nextSession = 0;

/** One response at a time; readable continuation tokens remain in transient memory. */
export function useRosterPage(filters: Filters) {
  const qc = useQueryClient();
  // Raw search participates so changed input immediately drops the previous view.
  const identity = JSON.stringify([filters.courseId, filters.sectionId, filters.search, filters.risk, filters.sort, filters.direction]);
  const [position, setPosition] = useState(() => ({ identity, session: ++nextSession, page: 1 }));
  const chain = useRef({ session: position.session, cursors: [undefined] as (string | undefined)[], asOf: null as string | null });
  const [submittedSearch, setSubmittedSearch] = useState(filters.search);
  if (position.identity !== identity) {
    const session = ++nextSession;
    chain.current = { session, cursors: [undefined], asOf: null };
    setPosition({ identity, session, page: 1 });
  }
  useEffect(() => {
    if (submittedSearch === filters.search) return;
    const timer = setTimeout(() => setSubmittedSearch(filters.search), 250);
    return () => clearTimeout(timer);
  }, [filters.search, submittedSearch]);

  const prefix = ['students', 'page', position.identity, position.session] as const;
  const cursor = chain.current.cursors[position.page - 1];
  const query = useQuery({
    queryKey: [...prefix, chain.current.asOf ?? 'start', position.page],
    enabled: position.identity === identity && submittedSearch === filters.search,
    gcTime: 0, staleTime: Infinity, retry: false,
    refetchOnWindowFocus: false, refetchOnMount: false,
    queryFn: ({ signal }) => {
      if (signal.aborted || chain.current.session !== position.session) throw new DOMException('Request cancelled', 'AbortError');
      const params = new URLSearchParams({ limit: '50', sort: filters.sort, dir: filters.direction });
      if (filters.courseId) params.set('course_id', filters.courseId);
      if (filters.sectionId) params.set('section_id', filters.sectionId);
      if (filters.search) params.set('q', filters.search);
      if (filters.risk) params.set('risk', filters.risk);
      return api<StudentPage>(`/students/page?${params}`, { signal, ...(cursor === undefined ? {} : { rosterCursor: cursor }) });
    },
  });

  const restart = useCallback(() => {
    if (chain.current.session !== position.session) return;
    const session = ++nextSession;
    chain.current = { session, cursors: [undefined], asOf: null };
    void qc.cancelQueries({ queryKey: ['students', 'page', position.identity, position.session] });
    setPosition({ identity: position.identity, session, page: 1 });
  }, [qc, position.identity, position.session]);

  useEffect(() => qc.getQueryCache().subscribe((event) => {
    if (event.type === 'updated' && event.action.type === 'invalidate') {
      const key = event.query.queryKey;
      if (key[0] === 'students' && key[1] === 'page' && key[2] === position.identity && key[3] === position.session) restart();
    }
  }), [qc, position.identity, position.session, restart]);

  useEffect(() => {
    const key = ['students', 'page', position.identity, position.session];
    return () => {
      void qc.cancelQueries({ queryKey: key });
      qc.removeQueries({ queryKey: key });
      if (chain.current.session === position.session) {
        chain.current.cursors = [undefined];
        chain.current.asOf = null;
      }
    };
  }, [qc, position.identity, position.session]);

  const ready = submittedSearch === filters.search && position.identity === identity && chain.current.session === position.session;
  const data = ready && !query.isFetching && !query.isError ? query.data : undefined;
  const next = () => {
    if (!data?.next_cursor || chain.current.session !== position.session) return;
    chain.current.asOf = data.as_of;
    chain.current.cursors = [...chain.current.cursors.slice(0, position.page), data.next_cursor];
    setPosition((p) => p.session === position.session && p.page === position.page ? { ...p, page: position.page + 1 } : p);
  };
  const previous = () => {
    if (!data || position.page === 1) return;
    if (position.page === 2) restart();
    else setPosition((p) => p.session === position.session && p.page === position.page ? { ...p, page: position.page - 1 } : p);
  };
  const invalidCursor = query.error instanceof ApiError && query.error.status === 400 && cursor !== undefined;
  return { data, error: ready ? query.error : null, loading: !ready || query.isPending || query.isFetching,
    page: position.page, next, previous, restart, invalidCursor, retry: () => query.refetch() };
}
