/** Theme management. The default is light/white, by product decision for this
 * first scaffold — unlike a typical app, this does NOT fall back to the OS's
 * prefers-color-scheme, so the page stays white unless the citizen (or a
 * later settings screen) explicitly asks for dark. */

const THEME_KEY = 'helaguide-theme';
const CONTRAST_KEY = 'helaguide-contrast';

export type Theme = 'light' | 'dark';
export type Contrast = 'normal' | 'high';

export function getInitialTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY);
  return saved === 'dark' ? 'dark' : 'light';
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
}

export function getInitialContrast(): Contrast {
  return localStorage.getItem(CONTRAST_KEY) === 'high' ? 'high' : 'normal';
}

export function applyContrast(level: Contrast): void {
  if (level === 'high') {
    document.documentElement.setAttribute('data-contrast', 'high');
  } else {
    document.documentElement.removeAttribute('data-contrast');
  }
  localStorage.setItem(CONTRAST_KEY, level);
}
