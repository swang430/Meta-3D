import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import MockAdapter from 'axios-mock-adapter'

import apiClient from '../src/api/client.ts'

test('syncs the current instrument configuration into the selected LabProfile', async () => {
  const service = await import('../src/api/labProfileService.ts') as Record<string, unknown>
  assert.equal(typeof service.syncCurrentInstrumentBinding, 'function')

  const syncCurrentInstrumentBinding = service.syncCurrentInstrumentBinding as (
    labProfileId: string,
    categoryKey: string,
  ) => Promise<Record<string, unknown>>
  const binding = {
    category_id: 'category-id',
    instrument_model_id: 'model-id',
    connection_endpoint: 'TCPIP0::192.168.100.22::inst0::INSTR',
    driver_mode: 'real',
    role: 'primary_baseStation',
  }
  const mock = new MockAdapter(apiClient)
  mock.onPut(
    '/lab-profiles/lab-id/instrument-bindings/baseStation/sync-current',
  ).reply(200, binding)

  try {
    assert.deepEqual(
      await syncCurrentInstrumentBinding('lab-id', 'baseStation'),
      binding,
    )
  } finally {
    mock.restore()
  }
})

test('equipment editor exposes explicit sync for the selected LabProfile', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const manager = app.slice(app.indexOf('function EquipmentManager()'))

  assert.match(manager, /selectedLabProfileId/)
  assert.match(manager, /syncCurrentInstrumentBinding\(selectedLabProfileId,\s*categoryKey\)/)
  assert.match(manager, /syncLabBindingMutation\.mutate\(category\.key\)/)
  assert.match(manager, /同步已保存配置到.*selectedLabProfile\?\.name/)
})

test('equipment editor keeps the drawer open so save feedback remains visible', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const manager = app.slice(app.indexOf('function EquipmentManager()'))

  assert.doesNotMatch(
    manager,
    /handleSaveConnection\(category\.key\);\s*setEditingCategoryKey\(null\)/,
  )
  assert.match(manager, /placeholder=\{CMW500_ROUTE_EXAMPLES\[field\]\}/)
  assert.match(manager, /保存失败: \$\{diagnosticErrorMessage\(error\)\}/)
})
