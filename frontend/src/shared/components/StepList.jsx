import Icon from './Icon.jsx';

const ICON = { concluida: 'check', erro: 'alert', pendente: 'pending' };
const WORD = { concluida: 'Concluída', andamento: 'Em andamento', pendente: 'Pendente', erro: 'Falhou' };

/** Etapas verticais. state: 'concluida' | 'andamento' | 'pendente' | 'erro'. */
export default function StepList({ steps = [] }) {
  return (
    <ol className="at-steps">
      {steps.map((s, i) => {
        const st = s.state || 'pendente';
        return (
          <li key={i} className={`at-step at-step--${st}`} aria-current={st === 'andamento' ? 'step' : undefined}>
            <span className="at-step__mark">
              {st === 'andamento' ? <span className="at-spinner" aria-hidden="true" /> : <Icon name={ICON[st]} size={18} />}
            </span>
            <span className="at-step__body">
              <span className="at-step__label">{s.label}</span>
              <span className="at-step__state">{s.detail || WORD[st]}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
