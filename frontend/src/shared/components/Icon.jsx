const PATHS = {
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  alert: ['M12 7.5v5.5', 'M12 16.4v.1', { c: [12, 12, 9] }],
  clock: ['M12 7v5l3 2', { c: [12, 12, 9] }],
  upload: ['M12 15V4', 'M7.5 8.5L12 4l4.5 4.5', 'M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4'],
  download: ['M12 4v11', 'M7.5 10.5L12 15l4.5-4.5', 'M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4'],
  play: ['M8 5.5v13l10.5-6.5z'],
  pause: ['M8.5 5v14', 'M15.5 5v14'],
  search: ['M15.8 15.8L20 20', { c: [11, 11, 6.5] }],
  copy: ['M15 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3', { r: [8, 8, 12, 12] }],
  close: ['M6 6l12 12', 'M18 6L6 18'],
  listen: ['M4 9.5h3.5L12 6v12l-4.5-3.5H4z', 'M15.5 9a4 4 0 0 1 0 6', 'M18 6.5a7.5 7.5 0 0 1 0 11'],
  merge: ['M6 4v4c0 3.5 2.5 6 6 6h6', 'M15 11l3 3-3 3', 'M6 20v-4'],
  edit: ['M4 20h4l11-11-4-4L4 16z', 'M13 7l4 4'],
  file: ['M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z', 'M14 3v5h5'],
  menu: ['M4 7h16', 'M4 12h16', 'M4 17h16'],
  plus: ['M12 5v14', 'M5 12h14'],
  retry: ['M19.5 12a7.5 7.5 0 1 1-2.2-5.3', 'M19.5 4.5v4h-4'],
  pending: [{ c: [12, 12, 7.5] }],
  chevron: ['M9 6l6 6-6 6'],
};

/** Ícone outline, traço 1,5 px, em currentColor. Tamanhos: 18 (controles), 20 (padrão), 24 (upload). */
export default function Icon({ name, size = 20, label, className }) {
  const parts = PATHS[name] || [];
  return (
    <svg
      className={['at-icon', className].filter(Boolean).join(' ')}
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden={label ? undefined : 'true'} role={label ? 'img' : undefined} aria-label={label}
    >
      {parts.map((d, i) =>
        typeof d === 'string' ? <path key={i} d={d} />
          : d.c ? <circle key={i} cx={d.c[0]} cy={d.c[1]} r={d.c[2]} />
            : <rect key={i} x={d.r[0]} y={d.r[1]} width={d.r[2]} height={d.r[3]} rx={1.5} />
      )}
    </svg>
  );
}

export const ICON_NAMES = Object.keys(PATHS);
