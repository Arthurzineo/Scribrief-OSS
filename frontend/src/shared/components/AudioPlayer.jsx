import Icon from './Icon.jsx';
import { clock } from '../lib/format.js';

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

/** Player controlado: tempos em segundos. */
export default function AudioPlayer({ playing, current = 0, duration = 0, speed = 1, disabled, onToggle, onSeek, onSpeed }) {
  const max = Math.max(1, duration);
  return (
    <div className="at-player">
      <button type="button" className="at-player__play" aria-label={playing ? 'Pausar' : 'Tocar'} onClick={onToggle} disabled={disabled}>
        <Icon name={playing ? 'pause' : 'play'} />
      </button>
      <span className="at-mono">{clock(current)}</span>
      <input
        type="range" className="at-player__line" min={0} max={max} step={0.1} value={Math.min(current, max)}
        aria-label="Linha do tempo" disabled={disabled}
        onChange={(e) => onSeek?.(Number(e.target.value))}
        style={{ '--at-pct': `${(Math.min(current, max) / max) * 100}%` }}
      />
      <span className="at-mono">{clock(duration)}</span>
      <select className="at-player__speed" value={String(speed)} aria-label="Velocidade" onChange={(e) => onSpeed?.(Number(e.target.value))} disabled={disabled}>
        {SPEEDS.map((v) => <option key={v} value={String(v)}>{String(v).replace('.', ',')}×</option>)}
      </select>
    </div>
  );
}
