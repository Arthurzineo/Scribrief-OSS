import Icon from './Icon.jsx';
import { speakerClass } from './speaker.js';

/** Linha do painel "Falantes": ponto, nome editável, tempo total e ações. */
export default function SpeakerRow({ index = 1, name, placeholder, total, onNameChange, onNameCommit, onListen, readOnly = false }) {
  return (
    <div className={['at-spkrow', speakerClass(index)].join(' ')}>
      <span className="at-spkdot" aria-hidden="true" />
      <input
        className="at-input at-spkrow__name"
        value={name}
        readOnly={readOnly}
        placeholder={placeholder || `Pessoa ${index}`}
        aria-label={`Nome do falante ${index}`}
        onChange={(e) => onNameChange?.(e.target.value)}
        onBlur={(e) => onNameCommit?.(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
      />
      <span className="at-mono at-spkrow__total" title="Tempo total de fala">{total}</span>
      <div className="at-spkrow__actions">
        <button type="button" className="at-link" onClick={onListen}><Icon name="listen" size={18} />Ouvir trecho</button>
      </div>
    </div>
  );
}
