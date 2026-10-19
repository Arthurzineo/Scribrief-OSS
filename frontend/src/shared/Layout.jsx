import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Button, Icon } from './components/index.js';
import { useAuth } from './context/AuthContext.jsx';
import { useMeetings } from './context/MeetingsContext.jsx';
import { statusInfo } from '../api/mappers.js';
import { dateBR } from './lib/format.js';

function initials(name) {
  return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
}

export default function Layout() {
  const { user } = useAuth();
  const { items } = useMeetings();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);

  return (
    <div className="shell">
      {open ? <button className="scrim" aria-label="Fechar menu" onClick={() => setOpen(false)} /> : null}
      <nav className={`side${open ? ' side--open' : ''}`} aria-label="Reuniões">
        <div className="side__brand"><button className="side__name" onClick={() => nav('/')}>Scribrief</button></div>
        <Button variant="primary" icon="plus" onClick={() => nav('/reunioes/nova')}>Nova reunião</Button>
        <div className="side__meetings">
          <p className="side__label">Reuniões</p>
          {items.length ? (
            <ul className="side__list">
              {items.map((m) => {
                const s = statusInfo(m);
                return (
                  <li key={m.id}>
                    <NavLink to={`/reunioes/${m.id}`} title={m.title} className={({ isActive }) => `side__item${isActive || loc.pathname.startsWith(`/reunioes/${m.id}/`) ? ' side__item--on' : ''}`}>
                      <span className="side__item-title">{m.title}</span>
                      <span className="side__item-meta">
                        <span className={`side__dot side__dot--${s.tone}`} aria-hidden="true" />
                        {dateBR(m.date)} · {s.label}
                      </span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          ) : <p className="side__label">Nenhuma ainda.</p>}
        </div>
        <div className="side__foot">
          <NavLink to="/conta" className={({ isActive }) => `side__account${isActive ? ' side__account--on' : ''}`}>
            <span className="side__avatar" aria-hidden="true">{initials(user?.name)}</span>
            <span>Conta</span>
          </NavLink>
        </div>
      </nav>
      <div className="main">
        <div className="topbar">
          <button className="topbar__btn" aria-label="Abrir menu" onClick={() => setOpen(true)}><Icon name="menu" /></button>
          <span className="topbar__name">Scribrief</span>
        </div>
        <main><Outlet /></main>
      </div>
    </div>
  );
}
