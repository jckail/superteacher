import type { SVGProps } from 'react';

/** Small stroke icon set in the spirit of SF Symbols: 24px grid, 1.7 stroke, rounded caps. Decorative by default. */
const PATHS = {
  today: <><path d="M3.5 11.2 12 4l8.5 7.2" /><path d="M5.5 9.8V19a1 1 0 0 0 1 1H10v-5.5h4V20h3.5a1 1 0 0 0 1-1V9.8" /></>,
  roster: <><circle cx="9" cy="8" r="3" /><path d="M3.5 19.2c.3-3 2.6-4.9 5.5-4.9s5.2 1.9 5.5 4.9" /><circle cx="17" cy="9" r="2.3" /><path d="M16.6 14.3c2.5.2 4.2 1.8 4.4 4.3" /></>,
  gradebook: <><rect x="3.5" y="4.5" width="17" height="15" rx="3" /><path d="M3.5 10h17M3.5 15h17M9.5 4.5v15" /></>,
  attendance: <><circle cx="12" cy="12" r="8.5" /><path d="m8.3 12.3 2.6 2.6 4.9-5.3" /></>,
  reports: <><rect x="5" y="3.5" width="14" height="17" rx="2.6" /><path d="M9 16.5v-3M12 16.5V9.5M15 16.5v-5" /></>,
  sparkles: <><path d="m11 4 1.6 4.4L17 10l-4.4 1.6L11 16l-1.6-4.4L5 10l4.4-1.6z" /><path d="M18 15v4M16 17h4" /></>,
  sun: <><circle cx="12" cy="12" r="3.8" /><path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M6 18l1.4-1.4M16.6 7.4 18 6" /></>,
  moon: <path d="M19.5 14.6A7.8 7.8 0 0 1 9.4 4.5a7.8 7.8 0 1 0 10.1 10.1z" />,
} as const;

export type IconName = keyof typeof PATHS;

export default function Icon({ name, className = 'ico', ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" className={className} {...rest}>{PATHS[name]}</svg>
  );
}
