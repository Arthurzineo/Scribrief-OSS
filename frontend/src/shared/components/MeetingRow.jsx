import StatusTag from './StatusTag.jsx';

/** Linha da lista de reuniões. Envolva as linhas em <div className="at-list">. */
export default function MeetingRow({ title, date, duration, speakers, tone, statusLabel, onClick }) {
  return (
    <button type="button" className="at-row" onClick={onClick}>
      <span className="at-row__title">{title}</span>
      <span className="at-row__meta">{date}</span>
      <span className="at-row__mono">{duration || '—'}</span>
      <span className="at-row__meta">{speakers ? `${speakers} ${speakers === 1 ? 'falante' : 'falantes'}` : '—'}</span>
      <span className="at-row__status"><StatusTag tone={tone}>{statusLabel}</StatusTag></span>
    </button>
  );
}
