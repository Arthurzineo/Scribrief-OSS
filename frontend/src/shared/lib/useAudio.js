import { useCallback, useEffect, useRef, useState } from 'react';

/** Player de áudio real para o `src` informado (URL do áudio da reunião). */
export default function useAudio(src) {
  const ref = useRef(null);
  const [state, setState] = useState({ playing: false, current: 0, duration: 0, speed: 1, error: false });

  useEffect(() => {
    if (!src) return undefined;
    const el = new Audio();
    el.preload = 'metadata';
    el.src = src;
    ref.current = el;
    const set = (p) => setState((o) => ({ ...o, ...p }));
    el.ontimeupdate = () => set({ current: el.currentTime });
    el.onloadedmetadata = () => set({ duration: Number.isFinite(el.duration) ? el.duration : 0 });
    el.onplay = () => set({ playing: true });
    el.onpause = () => set({ playing: false });
    el.onended = () => set({ playing: false });
    el.onerror = () => set({ error: true, playing: false });
    return () => { el.pause(); el.src = ''; ref.current = null; };
  }, [src]);

  const toggle = useCallback(() => {
    const el = ref.current; if (!el) return;
    if (el.paused) el.play().catch(() => {}); else el.pause();
  }, []);
  const seek = useCallback((t, play) => {
    const el = ref.current; if (!el) return;
    el.currentTime = Math.max(0, t);
    setState((o) => ({ ...o, current: el.currentTime }));
    if (play) el.play().catch(() => {});
  }, []);
  const setSpeed = useCallback((v) => {
    const el = ref.current; if (el) el.playbackRate = v;
    setState((o) => ({ ...o, speed: v }));
  }, []);

  return { ...state, available: !!src && !state.error, toggle, seek, setSpeed };
}
