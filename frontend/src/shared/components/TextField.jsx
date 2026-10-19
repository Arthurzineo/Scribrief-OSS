import { useId } from 'react';

/** Campo com rótulo acima. `error` troca a borda e a mensagem; `multiline` vira textarea. */
export default function TextField({ label, hint, error, multiline, className, id, ...rest }) {
  const auto = useId();
  const fid = id || auto;
  const msgId = `${fid}-msg`;
  const Tag = multiline ? 'textarea' : 'input';
  return (
    <div className={['at-field', className].filter(Boolean).join(' ')}>
      {label ? <label htmlFor={fid} className="at-field__label">{label}</label> : null}
      <Tag
        {...rest}
        id={fid}
        className={['at-input', multiline && 'at-input--multi', error && 'at-input--error'].filter(Boolean).join(' ')}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error || hint ? msgId : undefined}
      />
      {error ? <p id={msgId} className="at-field__msg at-field__msg--error">{error}</p>
        : hint ? <p id={msgId} className="at-field__msg">{hint}</p> : null}
    </div>
  );
}
