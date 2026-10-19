import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { usePageNavigate } from '../../shared/lib/pageNavigation.js';
import { Button, InlineNotice, StepList } from '../../shared/components/index.js';
import { buildMindMap } from '../../shared/lib/mindMap.js';
import { measureMindMapConnectors } from '../../shared/lib/mindMapConnectors.js';
import { dateBR } from '../../shared/lib/format.js';
import { exportMindMap } from '../../shared/lib/mindMapExport.js';
import { generateMindMap, getMindMap } from '../../api/meetings.js';

export default function MindMapView({ m }) {
  const navigate = usePageNavigate();
  const minutesPath = `/reunioes/${m.id}/ata`;
  const [mapState, setMapState] = useState({ status: 'loading', mapa: null });
  const [mapError, setMapError] = useState('');
  const map = buildMindMap(m, mapState.mapa);
  const canvasRef = useRef(null);
  const [connectors, setConnectors] = useState(null);
  const [exporting, setExporting] = useState(null);
  const [exportError, setExportError] = useState('');

  useLayoutEffect(() => {
    if (!map || !canvasRef.current) return undefined;
    const canvas = canvasRef.current;
    let frame = null;
    const measure = () => {
      const next = measureMindMapConnectors(canvas);
      setConnectors((previous) => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    };
    const schedule = () => {
      if (frame != null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    };
    measure();
    const observer = new ResizeObserver(schedule);
    for (const element of [canvas, ...canvas.querySelectorAll(
      '.mind-map__center, .mind-map__branch-title, .mind-map__card',
    )]) observer.observe(element);
    return () => { observer.disconnect(); if (frame != null) cancelAnimationFrame(frame); };
  }, [m.id, mapState.mapa]);

  const loadMap = useCallback(async () => {
    const result = await getMindMap(m.id);
    setMapState(result);
    return result;
  }, [m.id]);

  const requestMap = useCallback(async () => {
    setMapError('');
    setMapState({ status: 'generating', mapa: null });
    try { await generateMindMap(m.id); }
    catch (error) {
      setMapError(error.message || 'Não foi possível gerar o mapa. Tente novamente.');
      setMapState({ status: 'error', mapa: null });
    }
  }, [m.id]);

  useEffect(() => {
    if (!m.minutes || m.minutesStatus !== 'ready') return undefined;
    let active = true;
    getMindMap(m.id).then((result) => {
      if (!active) return;
      setMapState(result);
    }).catch((error) => {
      if (active) { setMapError(error.message); setMapState({ status: 'error', mapa: null }); }
    });
    return () => { active = false; };
  }, [m.id, m.minutesStatus, m.minutesVersion, m.minutesStale]);

  useEffect(() => {
    if (mapState.status !== 'generating') return undefined;
    const timer = setInterval(() => {
      loadMap().catch((error) => { setMapError(error.message); setMapState({ status: 'error', mapa: null }); });
    }, 3000);
    return () => clearInterval(timer);
  }, [mapState.status, loadMap]);

  async function handleExport(format) {
    if (exporting) return;
    setExportError('');
    setExporting(format);
    try {
      await exportMindMap(canvasRef.current, map.title, format);
    } catch (error) {
      setExportError(error?.message || 'Não foi possível baixar o mapa. Tente novamente.');
    } finally {
      setExporting(null);
    }
  }

  if (m.minutesStatus === 'generating') {
    return (
      <div className="mind-map__state">
        <StepList steps={[{ label: 'Gerando ata', state: 'andamento', detail: 'O mapa aparecerá quando a ata estiver pronta.' }]} />
      </div>
    );
  }
  if (!m.minutes) {
    return (
      <div className="mind-map__state">
        <InlineNotice tone={m.minutesStatus === 'failed' ? 'erro' : 'neutro'}>
          {m.minutesStatus === 'failed'
            ? 'Não foi possível gerar a ata. Tente novamente na aba Ata para criar o mapa.'
            : 'Ainda não há ata. Gere a ata para visualizar o mapa mental da reunião.'}
        </InlineNotice>
        <Button variant="primary" onClick={() => navigate(minutesPath)}>Ir para a ata</Button>
      </div>
    );
  }

  if (mapState.status === 'loading' || mapState.status === 'generating') {
    return <div className="mind-map__state"><p className="muted">{mapState.status === 'loading' ? 'Carregando mapa…' : 'Gerando mapa mental resumido…'}</p></div>;
  }

  if (!map) {
    return (
      <div className="mind-map__state">
        <InlineNotice tone={mapState.status === 'error' ? 'erro' : 'neutro'}>
          {mapError || (m.minutesStale
            ? 'A transcrição mudou. Atualize a ata antes de gerar o mapa.'
            : mapState.status === 'stale'
              ? 'A ata mudou. Gere novamente o mapa mental resumido.'
              : mapState.status === 'none'
                ? 'Gere um mapa curto com assuntos-chave. Esta ação faz uma chamada adicional à IA.'
                : 'Não foi possível gerar o mapa mental.')}
        </InlineNotice>
        {m.canEdit && !m.minutesStale ? <Button variant="primary" onClick={requestMap}>Gerar mapa mental</Button> : null}
        <Button onClick={() => navigate(minutesPath)}>Ir para a ata</Button>
      </div>
    );
  }

  return (
    <div className="mind-map">
      {m.minutesStale ? (
        <InlineNotice tone="processando">
          A transcrição mudou desde a geração da ata. Este mapa pode estar desatualizado.
        </InlineNotice>
      ) : null}
      <div className="mind-map__intro">
        <div>
          <h2 className="t-sec">Mapa mental</h2>
          <p>Assuntos-chave e frases curtas gerados por IA a partir da ata. Confira detalhes e contexto na ata e no áudio.</p>
        </div>
        <div className="mind-map__actions">
          <Button disabled={!!exporting} onClick={() => handleExport('png')}>{exporting === 'png' ? 'Gerando PNG…' : 'Baixar PNG'}</Button>
          <Button disabled={!!exporting} onClick={() => handleExport('pdf')}>{exporting === 'pdf' ? 'Gerando PDF…' : 'Baixar PDF'}</Button>
          <Button onClick={() => navigate(minutesPath)}>{m.canEdit ? 'Editar na ata' : 'Ver ata'}</Button>
          {m.canEdit ? <Button onClick={requestMap}>Gerar novamente</Button> : null}
        </div>
      </div>
      {exportError ? <InlineNotice tone="erro">{exportError}</InlineNotice> : null}
      <div className="mind-map__viewport" role="region" aria-label="Mapa mental com rolagem">
      <div className="mind-map__canvas" data-mind-map-export ref={canvasRef}>
        {connectors ? <svg className="mind-map__connectors" aria-hidden="true"
          viewBox={`0 0 ${connectors.width} ${connectors.height}`}>
          <path d={`M ${connectors.railLeft} ${connectors.trunkY} H ${connectors.railRight ?? connectors.rootX} M ${connectors.rootX} ${connectors.rootBottom} V ${connectors.trunkY}`} />
          <line x1={connectors.railLeft} y1={connectors.trunkY} x2={connectors.railLeft} y2={connectors.leftEnd} />
          {connectors.railRight != null ? <line x1={connectors.railRight} y1={connectors.trunkY} x2={connectors.railRight} y2={connectors.rightEnd} /> : null}
          {connectors.links.map((link) => <line key={link.id} data-branch-connector={link.id}
            x1={link.x1} y1={link.y} x2={link.x2} y2={link.y} />)}
          {connectors.children.map((branch) => <g key={branch.id}>
            <line data-branch-child-spine={branch.id} x1={branch.spineX} y1={branch.top}
              x2={branch.spineX} y2={branch.bottom} />
            {branch.links.map((link) => <line key={link.id} data-card-connector={link.id}
              x1={link.x1} y1={link.y} x2={link.x2} y2={link.y} />)}
          </g>)}
        </svg> : null}
        <div className="mind-map__center">
          <span className="mind-map__eyebrow">Reunião</span>
          <h3>{map.center}</h3>
          <span className="mind-map__date">{dateBR(map.date)}</span>
        </div>
        <div className="mind-map__branches">
          {map.branches.map((branch, index) => (
            <section className={`mind-map__branch mind-map__branch--${index % 2 === 0 ? 'left' : 'right'}`}
              key={branch.id} aria-labelledby={`map-${branch.id}`}>
              <h3 id={`map-${branch.id}`} className="mind-map__branch-title">
                {branch.label}
              </h3>
              {branch.items.length ? (
                <ol className="mind-map__items">
                  {branch.items.map((item) => (
                    <li className="mind-map__card" key={item.id}>
                      <h4>{item.title}</h4>
                    </li>
                  ))}
                </ol>
              ) : null}
            </section>
          ))}
        </div>
      </div>
      </div>
    </div>
  );
}
