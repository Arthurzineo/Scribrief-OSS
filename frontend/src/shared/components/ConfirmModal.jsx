import { useEffect, useRef } from 'react';
import Button from './Button.jsx';

/** Confirmação: título, uma frase, dois botões. Esc cancela; o foco vai para "Cancelar" e volta ao fechar. */
export default function ConfirmModal({ open = true, title, message, confirmLabel = 'Confirmar', cancelLabel = 'Cancelar', destructive, busy = false, onConfirm, onCancel }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const prev = document.activeElement;
    ref.current?.querySelector('.at-btn')?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onCancel?.(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="at-overlay">
      <div ref={ref} className="at-modal" role="dialog" aria-modal="true" aria-labelledby="at-modal-title">
        <h2 id="at-modal-title" className="at-modal__title">{title}</h2>
        <p className="at-modal__msg">{message}</p>
        <div className="at-modal__actions">
          <Button disabled={busy} onClick={onCancel}>{cancelLabel}</Button>
          <Button disabled={busy} variant={destructive ? 'destructive' : 'primary'} confirming={destructive} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
