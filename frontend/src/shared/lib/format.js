const pad = (n) => String(n).padStart(2, '0');
const MESES = ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.'];

/** 4368 → "01:12:48" (timestamps das falas). */
export function stamp(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
}
/** 4368 → "1:12:48" (duração da reunião). */
export function duration(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${Math.floor(s / 3600)}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
}
/** Relógio do player: "4:12" ou "1:12:48". */
export function clock(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, ss = s % 60;
  return h ? `${h}:${pad(m)}:${pad(ss)}` : `${m}:${pad(ss)}`;
}
/** Tempo total de fala: "18:22". */
export function minutes(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${Math.floor(s / 60)}:${pad(s % 60)}`;
}
/** "2026-10-08" ou ISO completo → "8 out. 2026". */
export function dateBR(value) {
  if (!value) return '—';
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return String(value);
  return `${d} ${MESES[m - 1]} ${y}`;
}
export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
export function fileSize(b) {
  if (b > 1e9) return `${(b / 1e9).toFixed(1).replace('.', ',')} GB`;
  if (b > 1e6) return `${(b / 1e6).toFixed(1).replace('.', ',')} MB`;
  return `${Math.max(1, Math.round(b / 1e3))} kB`;
}
export function slug(t) {
  return (t || 'reuniao').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'reuniao';
}
