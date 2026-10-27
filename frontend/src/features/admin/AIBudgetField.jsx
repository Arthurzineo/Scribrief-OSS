import { TextField } from '../../shared/components/index.js';

/** null = explicitly unlimited; an empty string = a limit still being entered. */
export default function AIBudgetField({ scope, value, onChange }) {
  const subject = scope === 'sector' ? 'do setor' : 'deste usuário';
  const unlimited = value == null;
  return <div>
    <label className="consent-control">
      <input type="checkbox" checked={unlimited}
        onChange={(event) => onChange(event.target.checked ? null : '')} />
      <span>Sem teto mensal de IA {subject}</span>
    </label>
    <TextField label={`Teto mensal estimado de IA ${subject} (US$)`}
      hint={scope === 'sector'
        ? 'Sem teto setorial não remove eventuais tetos pessoais. O consumo estimado continua sendo registrado.'
        : 'Sem teto pessoal não ignora o teto do setor, se houver. O consumo estimado continua sendo registrado.'}
      type="number" min="0.01" max="1000000" step="0.01"
      disabled={unlimited} required={!unlimited} value={value ?? ''}
      onChange={(event) => onChange(event.target.value)} />
  </div>;
}
