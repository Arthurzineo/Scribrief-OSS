import { dateBR, duration, stamp } from './format.js';

/*
 * Exportação da ata (PDF e TXT) e da transcrição (TXT), geradas no navegador.
 * A ata usa a paleta editorial do Scribrief:
 * azul #2E6CB1, azul-marinho #122357, dourado #CB9F35.
 */

function wrap(text, width) {
  const out = [];
  let line = '';
  String(text || '').split(/\s+/).forEach((w) => {
    if ((line + ' ' + w).trim().length > width) { out.push(line); line = w; } else line = line ? `${line} ${w}` : w;
  });
  if (line) out.push(line);
  return out.join('\n');
}

export function reviewLabel(minutes) {
  return minutes.reviewedAt
    ? `Ata revisada por ${minutes.reviewer} em ${new Date(minutes.reviewedAt).toLocaleString('pt-BR')}`
    : 'Ata não revisada';
}

/** meeting: { title, date, durationSeconds }; people: string[]; minutes includes topics[{title, comment}]. */
export function minutesToTxt(meeting, minutes, people) {
  const hr = '='.repeat(72), sub = '-'.repeat(72);
  const t = [
    'ATA DE REUNIÃO', hr, meeting.title, '',
    `Data: ${dateBR(meeting.date)}    Duração: ${duration(meeting.durationSeconds)}`,
    `Participantes: ${people.join(', ') || 'Não informados'}`,
    reviewLabel(minutes), '', '',
    'RESUMO EXECUTIVO', sub, wrap(minutes.summary, 72), '', '',
    'TÓPICOS DISCUTIDOS', sub,
  ];
  minutes.topics.forEach((topic, i) => t.push(`${i + 1}. ${topic.title}`, wrap(topic.comment, 72), ''));
  t.push('', 'DECISÕES', sub);
  minutes.decisions.forEach((d, i) => t.push(wrap(`${i + 1}. ${d}`, 72).replace(/\n/g, '\n   ')));
  t.push('', '', 'TAREFAS PENDENTES', sub);
  minutes.tasks.forEach((x, i) => t.push(`${i + 1}. ${x.task}`, `   Responsável: ${x.owner || '—'}    Prazo: ${x.due || '—'}`));
  return t.join('\n') + '\n';
}

/** groups: [{ name, segments: [{ start, text }] }] */
export function transcriptToTxt(meeting, groups) {
  const lines = ['TRANSCRIÇÃO', '='.repeat(72), meeting.title, `Data: ${dateBR(meeting.date)}    Duração: ${duration(meeting.durationSeconds)}`];
  groups.forEach((g) => {
    lines.push('', g.name.toUpperCase());
    g.segments.forEach((s) => lines.push(`[${stamp(s.start)}] ${wrap(s.text, 70).replace(/\n/g, '\n           ')}`));
  });
  return lines.join('\n') + '\n';
}

const C = {
  marinho: [18, 35, 87], azul: [46, 108, 177], dourado: [203, 159, 53], suave: [238, 243, 250],
  tinta: [28, 27, 25], tinta2: [92, 89, 82], borda: [221, 216, 206],
};

/** Carrega o jsPDF sob demanda (fica fora do pacote principal). */
export async function minutesToPdf(meeting, minutes, people) {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const W = 210, H = 297, M = 22, CW = W - 2 * M;
  let y = 0;
  const color = (c) => doc.setTextColor(c[0], c[1], c[2]);
  const ensure = (h) => { if (y + h > H - 22) { doc.addPage(); y = 22; } };
  const para = (text, font, style, size, lh, c) => {
    doc.setFont(font, style); doc.setFontSize(size); color(c);
    doc.splitTextToSize(String(text || ''), CW).forEach((ln) => { ensure(lh); doc.text(ln, M, y); y += lh; });
  };
  const heading = (text) => {
    y += 6; ensure(14);
    doc.setFont('times', 'bold'); doc.setFontSize(14); color(C.marinho); doc.text(text, M, y); y += 7.5;
  };

  doc.setFillColor(...C.azul); doc.rect(0, 0, W, 3, 'F');
  y = 20;
  doc.setFont('helvetica', 'bold'); doc.setFontSize(9); color(C.azul); doc.text('ATA DE REUNIÃO', M, y); y += 8;
  para(meeting.title, 'times', 'bold', 20, 8.5, C.marinho);
  y += 1;
  para(`${dateBR(meeting.date)}   ·   ${duration(meeting.durationSeconds)}   ·   Participantes: ${people.join(', ')}`, 'helvetica', 'normal', 9.5, 5, C.tinta2);
  para(reviewLabel(minutes), 'helvetica', 'bold', 9.5, 5, C.tinta2);
  y += 3; doc.setDrawColor(...C.dourado); doc.setLineWidth(0.5); doc.line(M, y, W - M, y); y += 6;

  heading('Resumo executivo'); para(minutes.summary, 'times', 'normal', 11.5, 6, C.tinta);
  heading('Tópicos discutidos');
  minutes.topics.forEach((topic, i) => {
    para(`${i + 1}. ${topic.title}`, 'times', 'bold', 12, 7, C.marinho);
    para(topic.comment, 'times', 'normal', 11.5, 6, C.tinta);
    y += 3;
  });

  heading('Decisões');
  minutes.decisions.forEach((d, i) => {
    doc.setFont('times', 'normal'); doc.setFontSize(11.5);
    const lines = doc.splitTextToSize(String(d), CW - 8);
    ensure(6 * lines.length + 1.5);
    doc.setFont('helvetica', 'bold'); doc.setFontSize(10.5); color(C.azul); doc.text(`${i + 1}.`, M, y);
    doc.setFont('times', 'normal'); doc.setFontSize(11.5); color(C.tinta);
    lines.forEach((ln) => { doc.text(ln, M + 8, y); y += 6; });
    y += 1.5;
  });

  heading('Tarefas pendentes');
  const cols = [CW * 0.56, CW * 0.26, CW * 0.18];
  const head = () => {
    ensure(9); doc.setFillColor(...C.suave); doc.rect(M, y - 5, CW, 8, 'F');
    doc.setFont('helvetica', 'bold'); doc.setFontSize(9.5); color(C.marinho);
    let x = M + 2;
    ['Tarefa', 'Responsável', 'Prazo'].forEach((t, i) => { doc.text(t, x, y); x += cols[i]; });
    doc.setDrawColor(...C.azul); doc.setLineWidth(0.35); doc.line(M, y + 3, W - M, y + 3); y += 9;
  };
  head();
  minutes.tasks.forEach((t) => {
    doc.setFont('helvetica', 'normal'); doc.setFontSize(10);
    const cells = [doc.splitTextToSize(String(t.task || ''), cols[0] - 4), doc.splitTextToSize(String(t.owner || '—'), cols[1] - 4), [String(t.due || '—')]];
    const rh = Math.max(cells[0].length, cells[1].length) * 5 + 3;
    if (y + rh > H - 22) { doc.addPage(); y = 22; head(); }
    color(C.tinta);
    let x = M + 2;
    cells.forEach((c, i) => { c.forEach((ln, k) => doc.text(ln, x, y + k * 5)); x += cols[i]; });
    y += rh - 1; doc.setDrawColor(...C.borda); doc.setLineWidth(0.25); doc.line(M, y - 2, W - M, y - 2); y += 3;
  });

  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i += 1) {
    doc.setPage(i); doc.setFont('helvetica', 'normal'); doc.setFontSize(8.5); color(C.tinta2);
    doc.text(meeting.title, M, H - 12, { maxWidth: CW - 30 });
    doc.text(`Página ${i} de ${pages}`, W - M, H - 12, { align: 'right' });
  }
  return doc.output('blob');
}
