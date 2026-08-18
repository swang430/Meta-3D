import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { evidenceViewFromDiagnosticRun } from '../src/features/Diagnostics/sequenceEvidence.ts'


test('historical complete evidence converts to the live result shape verbatim', () => {
  const view = evidenceViewFromDiagnosticRun({
    id: 'run-1',
    kind: 'scpi_sequence',
    target_name: 'raw_stub',
    success: false,
    run_at: '2026-08-18T12:00:00Z',
    sequence_evidence: {
      schema_version: 1,
      summary: 'instrument returned empty reply',
      duration_ms: 42,
      log: ['line one', 'line two'],
      steps: [{ label: 'STATE?', success: false, detail: 'empty', raw: '' }],
      extra: { nested: { observed: true } },
    },
  })

  assert.equal(view.kind, 'complete')
  if (view.kind !== 'complete') throw new Error('expected complete evidence')
  assert.equal(view.result.diagnostic_run_id, 'run-1')
  assert.equal(view.result.success, false)
  assert.equal(view.result.steps[0].raw, '')
  assert.deepEqual(view.result.log, ['line one', 'line two'])
  assert.deepEqual(view.result.extra, { nested: { observed: true } })
})

test('legacy rows remain explicitly unavailable and never parse the excerpt', () => {
  const view = evidenceViewFromDiagnosticRun({
    id: 'legacy-1',
    kind: 'scpi_sequence',
    target_name: 'old_sequence',
    success: true,
    run_at: '2026-08-01T00:00:00Z',
    output_excerpt: 'summary: fake\nraw: should-not-be-parsed',
    sequence_evidence: null,
  })

  assert.deepEqual(view, {
    kind: 'legacy',
    summary: '旧记录未持久化完整证据',
  })
})

test('recent runs fetch detail and expose a full-evidence action', () => {
  const panelSource = readFileSync(
    new URL('../src/features/Diagnostics/SequenceRunnerPanel.tsx', import.meta.url),
    'utf8',
  )
  assert.match(panelSource, /getDiagnosticRun/)
  assert.match(panelSource, /查看完整证据/)
  assert.match(panelSource, /evidenceViewFromDiagnosticRun/)
  assert.match(panelSource, /旧记录未持久化完整证据/)
})
