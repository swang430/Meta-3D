import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (relative: string) => readFileSync(new URL(relative, import.meta.url), 'utf8')

test('API mirrors expose the redacted server-owned channel operation evidence', () => {
  const generated = read('./api.generated.ts')
  const handwritten = read('./api.ts')

  for (const source of [generated, handwritten]) {
    assert.match(source, /ChannelEmulatorOperationEvidenceProjection/)
    assert.match(source, /channel_emulator_operation_evidence/)
    assert.match(source, /receipt_chain_digest/)
    assert.match(source, /exchange_ids/)
  }
  assert.doesNotMatch(generated, /ChannelOperationFieldEvidenceProjection[^}]*requested:/s)
  assert.doesNotMatch(generated, /ChannelOperationFieldEvidenceProjection[^}]*applied:/s)
})

test('history renders only the server status, reasons, and receipt digest', () => {
  const history = read('../features/TestManagement/components/HistoryTab/HistoryTab.tsx')
  const evidence = history.split('信道操作证据', 2)[1]

  assert.ok(evidence, 'history must expose the channel operation evidence section')
  assert.match(evidence, /channel_emulator_operation_evidence/)
  assert.match(evidence, /receipt_chain_digest/)
  assert.match(evidence, /\.reasons/)
  assert.match(evidence, /\.status/)
  assert.doesNotMatch(evidence, /\.requested/)
  assert.doesNotMatch(evidence, /\.applied/)
})
