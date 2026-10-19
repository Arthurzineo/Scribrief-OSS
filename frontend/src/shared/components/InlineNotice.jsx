/** Faixa curta de aviso. tone: 'destaque' (neutro) ou um estado. */
export default function InlineNotice({ tone = 'destaque', action, children }) {
  return (
    <div className={`at-notice at-notice--${tone}`} role={tone === 'erro' ? 'alert' : 'status'}>
      <span className="at-notice__text">{children}</span>
      {action || null}
    </div>
  );
}
