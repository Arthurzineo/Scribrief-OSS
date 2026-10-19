const KEY = 'ata-theme';

/** '' = segue o sistema; 'light' | 'dark' = escolha do usuário. */
export function readTheme() {
  try { return localStorage.getItem(KEY) || ''; } catch { return ''; }
}
export function applyTheme(t) {
  if (t) document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
  try { if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY); } catch { /* ignore */ }
}
export function effectiveTheme(t) {
  return t || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
