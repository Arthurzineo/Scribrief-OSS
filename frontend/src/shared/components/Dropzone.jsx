import Icon from './Icon.jsx';
import Button from './Button.jsx';

/** Arrastar e soltar; com `file`, mostra o envio com progresso (0..1) e "Cancelar". */
export default function Dropzone({ file, progress = 0, hint, accept = 'audio/*,video/*', dragging, onChange, onCancel, disabled }) {
  if (file) {
    const pct = Math.round(progress * 100);
    return (
      <div className="at-upload">
        <div className="at-upload__head">
          <Icon name="file" />
          <span className="at-upload__name">{file.name}</span>
          <span className="at-mono">{file.size}</span>
        </div>
        <div className="at-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Envio do arquivo">
          <span style={{ width: `${pct}%` }} />
        </div>
        <div className="at-upload__foot">
          <span className="at-mono">{pct}%</span>
          {onCancel ? <Button onClick={onCancel}>Cancelar</Button> : null}
        </div>
      </div>
    );
  }
  return (
    <label className={['at-drop', dragging && 'at-drop--over'].filter(Boolean).join(' ')}>
      <input type="file" className="at-sr" accept={accept} onChange={onChange} disabled={disabled} />
      <Icon name="upload" size={24} />
      <span className="at-drop__main">Arraste um arquivo de áudio ou vídeo, ou clique para escolher</span>
      {hint ? <span className="at-drop__hint">{hint}</span> : null}
    </label>
  );
}
