import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  describePathLossApplication,
  describePathLossSelection,
  parsePathLossApplication,
} from '../src/components/Commissioning/pathLossApplication.ts'


const application = (overrides: Record<string, unknown> = {}) => ({
  schema_version: 1,
  status: 'applied',
  provenance: 'unknown',
  reason: 'selected',
  gate_mode: 'mock_not_applicable',
  certificate_id: 'legacy-cert',
  value_disclosure: 'hidden_unverified',
  ...overrides,
})


test('applied unknown certificate is disclosed without showing compensation', () => {
  const view = describePathLossApplication(application())

  assert.match(view.message, /已应用路损补偿/)
  assert.match(view.message, /来源未知/)
  assert.equal(view.certificateId, 'legacy-cert')
  assert.equal(view.sourceLabel, '来源未知')
  assert.equal(view.showCompensationValue, false)
  assert.doesNotMatch(view.message, /未补偿/)
})


test('only applied explicit-real evidence may display the compensation value', () => {
  const verified = describePathLossApplication(application({
    provenance: 'real',
    value_disclosure: 'verified',
    certificate_id: 'real-cert',
  }))
  const simulated = describePathLossApplication(application({
    provenance: 'simulated',
  }))

  assert.equal(verified.showCompensationValue, true)
  assert.equal(verified.certificateId, 'real-cert')
  assert.equal(simulated.showCompensationValue, false)
  assert.match(simulated.message, /流程演练/)
})


test('missing and malformed history never infer application truth', () => {
  assert.deepEqual(parsePathLossApplication(undefined), {
    schema_version: 1,
    status: 'unknown',
    provenance: 'unknown',
    reason: 'legacy_unclassified',
    gate_mode: 'strict',
    certificate_id: null,
    value_disclosure: 'none',
  })
  assert.equal(
    describePathLossApplication({
      schema_version: 1,
      status: 'applied',
      provenance: 'invented',
    }).showCompensationValue,
    false,
  )
})


test('not-applied reasons remain distinct for precheck and measure views', () => {
  assert.match(
    describePathLossApplication(application({
      status: 'not_applied',
      provenance: 'missing',
      reason: 'expired',
      certificate_id: null,
      value_disclosure: 'none',
    })).message,
    /已过期/,
  )
  assert.equal(describePathLossSelection('missing', false), '未找到匹配证书')
  assert.equal(describePathLossSelection('expired', false), '匹配证书已过期')
  assert.equal(describePathLossSelection('frequency_mismatch', false), '证书频率不匹配')
  assert.equal(describePathLossSelection('operating_mode_mismatch', false), '证书 RF 模式不匹配')
})


test('commissioning phases consume the shared view instead of guessing from verified', () => {
  const source = readFileSync(
    new URL('../src/components/Commissioning/Phases.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /describePathLossApplication\(data\.path_loss_application\)/)
  assert.match(source, /describePathLossSelection\(/)
  assert.doesNotMatch(
    source,
    /path_loss_verified\s*!==\s*true[\s\S]{0,400}无 path-loss certificate/,
  )
})
