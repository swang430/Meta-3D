import assert from 'node:assert/strict'
import test from 'node:test'

import {
  formatBaseStationSyncTruth,
  projectBaseStationBindingTruth,
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
