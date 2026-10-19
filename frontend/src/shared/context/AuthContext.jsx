import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import * as auth from '../../api/auth.js';

const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    auth.getMe().then((u) => { if (alive) setUser(u); }).catch(() => {}).finally(() => { if (alive) setReady(true); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const onUnauth = () => setUser(null);
    window.addEventListener('ata:unauthorized', onUnauth);
    return () => window.removeEventListener('ata:unauthorized', onUnauth);
  }, []);

  const login = useCallback(async (email, password) => {
    const u = await auth.login(email, password);
    setUser(u || (await auth.getMe()));
  }, []);
  const logout = useCallback(async () => { try { await auth.logout(); } finally { setUser(null); } }, []);

  return <Ctx.Provider value={{ user, setUser, ready, login, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
