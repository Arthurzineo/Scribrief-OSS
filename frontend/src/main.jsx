import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import { AuthProvider } from './shared/context/AuthContext.jsx';
import { ToastProvider } from './shared/context/ToastContext.jsx';
import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import '@fontsource/source-serif-4/latin-400.css';
import '@fontsource/source-serif-4/latin-600.css';
import './styles/tokens.css';
import './styles/components.css';
import './styles/app.css';

const menu = document.getElementById('mvt-menu-toggle');
if (menu) {
  const side = document.querySelector('.side');
  const scrim = document.createElement('button');
  scrim.className = 'scrim';
  scrim.type = 'button';
  scrim.setAttribute('aria-label', 'Fechar menu');
  scrim.hidden = true;
  side.parentNode.insertBefore(scrim, side);
  const close = () => { side.classList.remove('side--open'); scrim.hidden = true; };
  menu.addEventListener('click', () => { side.classList.add('side--open'); scrim.hidden = false; });
  scrim.addEventListener('click', close);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
