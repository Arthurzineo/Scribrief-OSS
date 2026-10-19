import SpeakerTag from './SpeakerTag.jsx';
import Button from './Button.jsx';
import { speakerClass } from './speaker.js';

/**
 * Falas seguidas de um mesmo falante.
 * segments: [{ key, domId, time (texto hh:mm:ss), seconds, text, active }]
 * onSeek(seconds) ao clicar no timestamp; onEdit(segmentIndex, texto) ao sair da edição.
 */
export default function Utterance({ speakerIndex = 1, speakerName, segments = [], editable, onSeek, onEdit, onAccept, onReject, deciding }) {
  return (
    <section className={['at-utt', speakerClass(speakerIndex)].join(' ')}>
      <header className="at-utt__head"><SpeakerTag index={speakerIndex} name={speakerName} /></header>
      {segments.map((s, i) => (
        <div id={s.domId} key={s.key ?? i} className={s.active ? 'at-utt__seg at-utt__seg--active' : 'at-utt__seg'} aria-current={s.active ? 'true' : undefined}>
          <p
            className="at-utt__text"
            contentEditable={editable ? 'true' : undefined}
            suppressContentEditableWarning
            role={editable ? 'textbox' : undefined}
            aria-label={editable ? 'Texto da fala' : undefined}
            onBlur={onEdit ? (e) => onEdit(i, e.currentTarget.textContent) : undefined}
          >
            {s.text}
          </p>
          <button type="button" className="at-time" onClick={() => onSeek?.(s.seconds)} aria-label={`Ouvir a partir de ${s.time}${s.active ? ', trecho atual' : ''}`}>
            {s.active ? <span className="at-time__current" aria-hidden="true">●</span> : null}{s.time}
          </button>
          {s.suggestion ? (
            <div className="at-utt__suggestion" aria-label="Sugestão de correção da IA">
              <span className="at-utt__suggestion-label">Possível correção · confira ouvindo o áudio</span>
              <p>{s.suggestion.texto_sugerido}</p>
              <small>{s.suggestion.motivo}</small>
              <div className="at-utt__suggestion-actions">
                <Button variant="primary" disabled={deciding != null} onClick={() => onAccept?.(s.key)}>Aceitar</Button>
                <Button disabled={deciding != null} onClick={() => onReject?.(s.key)}>Negar</Button>
              </div>
            </div>
          ) : null}
        </div>
      ))}
    </section>
  );
}
