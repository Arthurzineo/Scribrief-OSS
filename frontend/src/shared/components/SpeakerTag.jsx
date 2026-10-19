import { speakerClass } from './speaker.js';

/** Ponto na cor do falante + nome em tinta. `index` começa em 1. */
export default function SpeakerTag({ index = 1, name, className }) {
  return (
    <span className={['at-spktag', speakerClass(index), className].filter(Boolean).join(' ')}>
      <span className="at-spkdot" aria-hidden="true" />
      <span className="at-spktag__name">{name || `Pessoa ${index}`}</span>
    </span>
  );
}
