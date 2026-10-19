import Icon from './Icon.jsx';

const STATUS = {
  sucesso: ['check', 'Pronta'],
  processando: ['clock', 'Processando'],
  erro: ['alert', 'Erro'],
  neutro: ['pending', 'Aguardando'],
};

/** Estado sempre com texto e ícone. tone: 'sucesso' | 'processando' | 'erro' | 'neutro'. */
export default function StatusTag({ tone, children }) {
  const s = STATUS[tone] ? tone : 'neutro';
  return (
    <span className={`at-status at-status--${s}`}>
      <Icon name={STATUS[s][0]} size={14} />
      {children || STATUS[s][1]}
    </span>
  );
}
