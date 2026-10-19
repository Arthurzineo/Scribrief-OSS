/** Adapta somente o mapa compacto gerado pela IA; nunca projeta a ata integral. */
export function buildMindMap(meeting, data) {
  if (!data || !Array.isArray(data.ramos)) return null;
  return {
    title: meeting.title,
    date: meeting.date,
    center: data.centro,
    branches: data.ramos.map((branch, index) => ({
      id: `branch-${index}`,
      label: branch.titulo,
      items: (branch.pontos || []).map((point, pointIndex) => ({
        id: `point-${index}-${pointIndex}`,
        title: point,
      })),
    })),
  };
}
