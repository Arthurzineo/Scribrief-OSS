import Icon from './Icon.jsx';

/** variant: 'primary' | 'secondary' | 'destructive'. `confirming` só no botão de confirmação de ação destrutiva. */
export default function Button({ variant = 'secondary', icon, confirming, className, children, type = 'button', ...rest }) {
  const cls = ['at-btn', `at-btn--${variant}`, confirming && 'at-btn--confirming', className].filter(Boolean).join(' ');
  return (
    <button type={type} {...rest} className={cls}>
      {icon ? <Icon name={icon} size={18} /> : null}
      {children}
    </button>
  );
}
