/** Alternador "Transcrição" / "Ata". */
export default function ViewTabs({ items, active, onChange }) {
  return (
    <div className="at-tabs" role="tablist">
      {items.map((it) => (
        <button key={it} type="button" role="tab" aria-selected={it === active} className={['at-tab', it === active && 'at-tab--on'].filter(Boolean).join(' ')} onClick={() => onChange?.(it)}>
          {it}
        </button>
      ))}
    </div>
  );
}
