/** Classe de cor do falante: 1..8 ciclam; do 9º em diante, ponto em contorno. */
export function speakerClass(index) {
  const i = Math.max(1, index || 1);
  const n = ((i - 1) % 8) + 1;
  return ['at-spk--' + n, i > 8 && 'at-spk--outline'].filter(Boolean).join(' ');
}
