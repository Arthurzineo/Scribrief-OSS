import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { listMeetings } from '../../api/meetings.js';
import { isProcessing } from '../../api/mappers.js';

const Ctx = createContext(null);
const POLL_MS = 10000;

/** Lista de reuniões compartilhada pela barra lateral e pela tela inicial. Atualiza sozinha enquanto houver processamento. */
export function MeetingsProvider({ children }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const polling = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const list = await listMeetings();
      setItems(list);
      setError(null);
      return list;
    } catch (e) {
      setError(e);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!items.some((m) => isProcessing(m) || m.minutesStatus === 'generating')) return undefined;
    const timer = setInterval(async () => {
      if (polling.current) return;
      polling.current = true;
      try { await refresh(); } finally { polling.current = false; }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [items, refresh]);

  return <Ctx.Provider value={{ items, loading, error, refresh }}>{children ?? <Outlet />}</Ctx.Provider>;
}

export const useMeetings = () => useContext(Ctx);
