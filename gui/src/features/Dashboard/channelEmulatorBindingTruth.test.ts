import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  formatChannelEmulatorSyncTruth,
  projectChannelEmulatorBindingTruth,
} from './channelEmulatorBindingTruth.ts'
import { projectReadinessVerdict } from './baseStationBindingTruth.ts'

const configured = {
  status: 'configured' as const,
  binding_digest: 'fedcba9876543210',
  execution_mode: 'real' as const,
  adapter_id: 'propsim_f64',
  model_name: 'PROPSIM F64',
  category_id: 'category-id',
  instrument_model_id: 'model-id',
  instrument_connection_id: 'connection-id',
  lab_profile_id: 'lab-id',
  resolved_binding: {},
  runtime_driver: {},
  detail: 'resolved',
  selected_asset_id: null,
}

test('real configured binding is green and exposes the same identity digest', () => {
  const truth = projectChannelEmulatorBindingTruth(configured)
  assert.equal(truth.light, 'green')
  assert.match(truth.valueText, /propsim_f64/)
  assert.match(truth.detail, /PROPSIM F64/)
  assert.match(truth.detail, /connection-id/)
  assert.match(truth.detail, /fedcba987654/)
  assert.doesNotMatch(truth.detail, /资产/)
  assert.match(
    formatChannelEmulatorSyncTruth({ ...configured, selected_asset_id: 'asset-1' }),
    /资产 asset-1/,
  )
})

test('not_applicable with a real driver mirrors BaseStation and stays green', () => {
  assert.equal(
    projectChannelEmulatorBindingTruth({ ...configured, status: 'not_applicable' }).light,
    'green',
  )
})

test('simulated and unbound bindings stay diagnostic yellow', () => {
  assert.equal(
    projectChannelEmulatorBindingTruth({ ...configured, execution_mode: 'simulated' }).light,
    'yellow',
  )
  const unbound = projectChannelEmulatorBindingTruth({
    ...configured,
    status: 'diagnostic_unbound',
    execution_mode: 'simulated',
    binding_digest: null,
    adapter_id: null,
    model_name: null,
    instrument_model_id: null,
    instrument_connection_id: null,
  })
  assert.equal(unbound.light, 'yellow')
  assert.equal(unbound.valueText, '仅诊断')
  assert.match(unbound.detail, /未解析 adapter/)
})

test('invalid or absent binding is red, is visible as a conflict, and blocks the verdict', () => {
  const invalid = projectChannelEmulatorBindingTruth({
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
    detail: '驱动连接身份 / transport 与所选连接不一致',
  })
  assert.equal(invalid.light, 'red')
  assert.equal(invalid.valueText, '配置冲突')
  assert.match(invalid.detail, /不一致/)
  assert.equal(projectChannelEmulatorBindingTruth(null).light, 'red')
  assert.equal(projectChannelEmulatorBindingTruth(undefined).valueText, '未解析')

  const verdict = projectReadinessVerdict(
    [
      {
        key: 'channel-emulator-binding',
        title: '信道仿真器绑定',
        light: invalid.light,
        valueText: invalid.valueText,
      },
    ],
    true,
  )
  assert.equal(verdict.light, 'red')
  assert.match(verdict.text, /信道仿真器绑定（配置冲突）/)
})

test('diagnostic channelEmulator binding turns the aggregate verdict yellow instead of formally ready', () => {
  const binding = projectChannelEmulatorBindingTruth({ ...configured, execution_mode: 'simulated' })
  const verdict = projectReadinessVerdict(
    [
      {
        key: 'channel-emulator-binding',
        title: '信道仿真器绑定',
        light: binding.light,
        valueText: binding.valueText,
      },
    ],
    true,
  )
  assert.equal(verdict.light, 'yellow')
  assert.match(verdict.text, /仅可诊断：信道仿真器绑定/)
})

test('readiness strip consumes the channelEmulator binding through the shared projection', () => {
  const readiness = readFileSync(new URL('./ZoneReadiness.tsx', import.meta.url), 'utf8')
  assert.match(readiness, /projectChannelEmulatorBindingTruth\(report\.channel_emulator_binding\)/)
  const cell = readiness.slice(
    readiness.indexOf("key: 'channel-emulator-binding'"),
    readiness.indexOf("key: 'base-station-compatibility'"),
  )
  assert.ok(cell.length > 0)
  assert.match(cell, /title: '信道仿真器绑定'/)
  // 灯色只能来自投影，不许在单元格里硬编码
  assert.match(cell, /light: channelEmulatorBinding\.light/)
  assert.doesNotMatch(cell, /light: '(green|yellow|red|gray)'/)
})
