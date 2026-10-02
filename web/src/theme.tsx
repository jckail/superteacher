import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

type Theme = 'light' | 'dark';
const ThemeContext = createContext<[boolean, () => void]>([false, () => {}]);

/** One preference shared by sign-in and the authenticated shell. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem('st-theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch { /* storage can be disabled */ }
    return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('st-theme', theme); } catch { /* storage can be disabled */ }
  }, [theme]);
  return <ThemeContext.Provider value={[theme === 'dark', () => setTheme((current) => current === 'dark' ? 'light' : 'dark')]}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
