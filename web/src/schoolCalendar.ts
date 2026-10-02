import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { SchoolCalendar } from './types';

export function useSchoolCalendar(enabled = true) {
  return useQuery({
    queryKey: ['school-calendar'],
    queryFn: async ({ signal }) => {
      const calendar = await api<SchoolCalendar>('/calendar', { signal });
      if (!calendar || typeof calendar.timezone !== 'string' || typeof calendar.today !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(calendar.today)) {
        throw new Error('The school day could not be determined. Please retry.');
      }
      return calendar;
    },
    enabled,
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: false,
  });
}
