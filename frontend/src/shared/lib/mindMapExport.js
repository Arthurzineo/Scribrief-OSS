import { downloadFile } from './download.js';
import { slug } from './format.js';

const EXPORT_WIDTH = 1120;

function canvasBlob(canvas, type) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('Não foi possível criar a imagem do mapa.')), type);
  });
}

/** Renderiza apenas os cartões do mapa, sempre em largura de desktop e tema claro. */
async function captureMap(element) {
  const exportWidth = Math.max(EXPORT_WIDTH, Math.ceil(element.getBoundingClientRect().width));
  const { default: html2canvas } = await import('html2canvas');
  const canvas = await html2canvas(element, {
    backgroundColor: '#ffffff',
    scale: 1,
    windowWidth: Math.max(1280, exportWidth + 160),
    useCORS: true,
    onclone: (documentClone) => {
      documentClone.documentElement.setAttribute('data-theme', 'light');
      const mapClone = documentClone.querySelector('[data-mind-map-export]');
      if (!mapClone) throw new Error('Mapa indisponível para exportação.');
      const viewportClone = mapClone.closest('.mind-map__viewport');
      if (viewportClone) {
        viewportClone.style.maxHeight = 'none';
        viewportClone.style.overflow = 'visible';
        viewportClone.style.width = `${exportWidth}px`;
      }
      mapClone.style.boxSizing = 'border-box';
      mapClone.style.width = `${exportWidth}px`;
      mapClone.style.maxWidth = 'none';
    },
  });
  if (!canvas.width || !canvas.height) throw new Error('O mapa está vazio.');
  return canvas;
}

/** Exporta a mesma visualização exibida na aba, sem nova chamada de IA. */
export async function exportMindMap(element, title, format) {
  if (!element) throw new Error('Mapa indisponível para exportação.');
  if (!['png', 'pdf'].includes(format)) throw new Error('Formato de exportação inválido.');
  const canvas = await captureMap(element);
  const filename = `mapa-mental-${slug(title)}.${format}`;
  if (format === 'png') {
    downloadFile(filename, await canvasBlob(canvas, 'image/png'));
    return;
  }

  const { jsPDF } = await import('jspdf');
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
  const margin = 10;
  const pageWidth = pdf.internal.pageSize.getWidth() - 2 * margin;
  const pageHeight = pdf.internal.pageSize.getHeight() - 2 * margin;
  const sliceHeight = Math.max(1, Math.floor(canvas.width * pageHeight / pageWidth));
  const imageHeight = (height) => height * pageWidth / canvas.width;
  for (let start = 0, page = 0; start < canvas.height; start += sliceHeight, page += 1) {
    const height = Math.min(sliceHeight, canvas.height - start);
    const slice = document.createElement('canvas');
    slice.width = canvas.width;
    slice.height = height;
    const context = slice.getContext('2d');
    if (!context) throw new Error('Não foi possível paginar o mapa.');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, slice.width, slice.height);
    context.drawImage(canvas, 0, start, canvas.width, height, 0, 0, canvas.width, height);
    if (page) pdf.addPage();
    pdf.addImage(slice.toDataURL('image/png'), 'PNG', margin, margin, pageWidth, imageHeight(height));
    slice.width = 0;
    slice.height = 0;
  }
  downloadFile(filename, pdf.output('blob'));
}
