import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatBaseStationSyncTruth,
  projectBaseStationBindingTruth,
  projectBaseStationCompatibilityTruth,
  projectReadinessVerdict,
} from './baseStationBindingTruth.ts'

const configured = {
  status: 'configured' as const,
  binding_digest: '0123456789abcdef',
  execution_mode: 'real' as const,
  adapter_id: 'cmw500',
  model_name: 'CMW500',
  category_id: 'category-id',
  instrument_model_id: 'model-id',
  instrument_connection_id: 'connection-id',
  lab_profile_id: 'lab-id',
  resolved_binding: {},
  runtime_driver: {},
  detail: 'resolved',
}

test('real resolved binding is green and exposes the same identity digest', () => {
  const truth = projectBaseStationBindingTruth(configured)
  assert.equal(truth.light, 'green')
  assert.match(truth.valueText, /cmw500/)
  assert.match(truth.detail, /CMW500/)
  assert.match(truth.detail, /connection-id/)
  assert.match(truth.detail, /0123456789ab/)
  assert.match(formatBaseStationSyncTruth(configured), /0123456789ab/)
})

test('simulated and unbound bindings stay diagnostic yellow', () => {
  assert.equal(
    projectBaseStationBindingTruth({ ...configured, execution_mode: 'simulated' }).light,
    'yellow',
  )
  assert.equal(
    projectBaseStationBindingTruth({
      ...configured,
      status: 'diagnostic_unbound',
      binding_digest: null,
      adapter_id: null,
      model_name: null,
      instrument_model_id: null,
      instrument_connection_id: null,
    }).light,
    'yellow',
  )
})

test('invalid or absent binding is red and never contributes a green verdict', () => {
  const invalid = projectBaseStationBindingTruth({
    ...configured,
    status: 'invalid',
    binding_digest: null,
    execution_mode: null,
    adapter_id: null,
    model_name: null,
    category_id: null,
    instrument_model_id: null,
    instrument_connection_id: null,
    resolved_binding: null,
    runtime_driver: null,
    detail: 'selected connection drifted',
  })
  assert.equal(invalid.light, 'red')
  assert.match(invalid.detail, /drifted/)
  assert.equal(projectBaseStationBindingTruth(null).light, 'red')
})

test('diagnostic binding makes the aggregate verdict yellow instead of formally ready', () => {
  const binding = projectBaseStationBindingTruth({
    ...configured,
    execution_mode: 'simulated',
  })
  const verdict = projectReadinessVerdict(
    [
      {
        key: 'base-station-binding',
        title: '基站绑定',
        light: binding.light,
        valueText: binding.valueText,
      },
    ],
    true,
  )

  assert.equal(verdict.light, 'yellow')
  assert.match(verdict.text, /仅可诊断/)
  assert.doesNotMatch(verdict.text, /✅ 可开测/)
})

test('aggregate verdict preserves unavailable, blocking, and formal-ready states', () => {
  const cell = {
    key: 'drivers',
    title: '驱动链',
    light: 'green' as const,
    valueText: '全部 ok',
  }
  assert.equal(projectReadinessVerdict([cell], false).light, 'red')
  assert.equal(
    projectReadinessVerdict([{ ...cell, light: 'red', valueText: '1 个失败' }], true)
      .light,
    'red',
  )
  assert.deepEqual(projectReadinessVerdict([cell], true), {
    light: 'green',
    text: '✅ 可开测',
  })
})

const compatible = {
  schema_version: 1 as const,
  status: 'compatible' as const,
  compatible: true,
  test_case_id: 'case-id',
  lab_profile_id: 'lab-id',
  binding_digest: '0123456789abcdef',
  execution_mode: 'real' as const,
  requirements: {
    schema_version: 1 as const,
    requested_rat: 'nr5g' as const,
    required_operations: ['identity'],
    mac_profile: null,
  },
  verdict: {
    schema_version: 1 as const,
    status: 'compatible' as const,
    compatible: true,
    reasons: [],
    requirements_digest: 'requirements-digest',
    manifest_digest: 'manifest-digest',
  },
  reasons: [],
  detail: 'compatible',
}

test('TestCase compatibility is green only for a real compatible binding', () => {
  assert.equal(projectBaseStationCompatibilityTruth(compatible).light, 'green')
  assert.equal(
    projectBaseStationCompatibilityTruth({
      ...compatible,
      execution_mode: 'simulated',
    }).light,
    'yellow',
  )
  assert.equal(
    projectBaseStationCompatibilityTruth({
      ...compatible,
      status: 'no_adapter',
      binding_digest: null,
      verdict: { ...compatible.verdict, status: 'no_adapter', manifest_digest: null },
    }).light,
    'yellow',
  )
})

test('incompatible, invalid, not-evaluated, and absent contexts are red', () => {
  for (const status of ['incompatible', 'invalid', 'not_evaluated'] as const) {
    const truth = projectBaseStationCompatibilityTruth({
      ...compatible,
      status,
      compatible: status === 'not_evaluated' ? null : false,
      verdict: status === 'incompatible'
        ? { ...compatible.verdict, status, compatible: false, reasons: ['RAT mismatch'] }
        : null,
      reasons: ['saved context is not ready'],
    })
    assert.equal(truth.light, 'red')
  }
  assert.equal(projectBaseStationCompatibilityTruth(null).light, 'red')
})

test('any diagnostic yellow readiness cell keeps the aggregate diagnostic', () => {
  const verdict = projectReadinessVerdict(
    [{ key: 'base-station-compatibility', title: '用例兼容性', light: 'yellow', valueText: '仅诊断' }],
    true,
  )
  assert.equal(verdict.light, 'yellow')
  assert.match(verdict.text, /仅可诊断/)
})
