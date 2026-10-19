import { useState } from 'react';
import { generateMinutes, retryMeeting } from '../../api/meetings.js';

/** Inicia a geração da ata; a página acompanha o minutesStatus por polling. */
export default function useGenerate(m, setM, refreshList, say) {
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      if (m.minutesStatus === 'failed') await retryMeeting(m.id);
      else await generateMinutes(m.id);
      setM({ ...m, minutesStatus: 'generating', minutesError: null });
      refreshList();
      return true;
    } catch (e) {
      say(`Não foi possível gerar a ata. ${e.message}`);
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}
