/** Retorna a fala no instante do áudio, sem atribuir silêncio a uma fala. */
export function activeSegmentId(segments, seconds) {
  if (!Number.isFinite(seconds)) return null;
  let active = null;
  for (const segment of segments) {
    if (segment.start <= seconds && seconds < segment.end) {
      if (!active || segment.start >= active.start) active = segment;
    }
  }
  return active?.id ?? null;
}
