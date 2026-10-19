import { createContext, useCallback, useContext, useRef, useState } from 'react';

const Ctx = createContext(() => {});

export function ToastProvider({ children }) {
  const [msg, setMsg] = useState(null);
  const t = useRef(null);
  const say = useCallback((m) => {
    setMsg(m);
    clearTimeout(t.current);
    t.current = setTimeout(() => setMsg(null), 2800);
  }, []);
  return (
    <Ctx.Provider value={say}>
      {children}
      {msg ? <div className="toast" role="status">{msg}</div> : null}
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
