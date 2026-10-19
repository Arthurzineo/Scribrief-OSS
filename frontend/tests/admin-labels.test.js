import assert from 'node:assert/strict';
import { test } from 'node:test';
import { actionLabel, componentLabel, jobLabel, outcomeLabel, severityLabel, targetLabel } from '../src/features/admin/adminLabels.js';

test('códigos operacionais conhecidos são exibidos em português', () => {
  assert.equal(jobLabel('transcription'), 'Transcrição');
  assert.equal(jobLabel('running'), 'Em execução');
  assert.equal(jobLabel('transcribing'), 'Transcrevendo');
  assert.equal(actionLabel('login'), 'Entrou no sistema');
  assert.equal(actionLabel('job_failed'), 'Tarefa falhou');
  assert.equal(outcomeLabel('failed'), 'Falhou');
  assert.equal(targetLabel('meeting'), 'Reunião');
  assert.equal(componentLabel('worker'), 'Processador de tarefas');
  assert.equal(severityLabel('warning'), 'Aviso');
});

test('códigos inesperados não exibem valores brutos em inglês', () => {
  assert.equal(jobLabel('new_provider_stage'), 'Etapa não catalogada');
  assert.equal(actionLabel('new_audit_action'), 'Ação não catalogada');
  assert.equal(outcomeLabel('new_outcome'), 'Resultado não catalogado');
});
