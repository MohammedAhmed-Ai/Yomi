import { useCallback, useEffect, useState } from 'react';
import type { ReactElement } from 'react';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'yomi-theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

function storedTheme(): Theme | null {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'light' || stored === 'dark' ? stored : null;
}

function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
}

/** An explicit choice wins; otherwise follow the OS. */
function initialTheme(): Theme {
  return storedTheme() ?? systemTheme();
}

function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark');
}

export function ThemeToggle(): ReactElement {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  const toggle = useCallback(() => {
    setTheme((previous) => {
      const next: Theme = previous === 'dark' ? 'light' : 'dark';
      localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
      return next;
    });
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Track the OS live, but only while the user has not chosen for themselves.
  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY);
    const onChange = (event: MediaQueryListEvent): void => {
      if (storedTheme() !== null) return;
      const next: Theme = event.matches ? 'dark' : 'light';
      setTheme(next);
      applyTheme(next);
    };

    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      className="press inline-flex items-center justify-center rounded-[12px] border border-border bg-surface px-2 py-1 text-text transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      {theme === 'dark' ? '🌙' : '☀️'}
    </button>
  );
}