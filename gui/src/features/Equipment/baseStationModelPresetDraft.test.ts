import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  draftForBaseStationModel,
  explicitBaseStationConnectionDraft,
} from './baseStationModelPresetDraft.ts'
import type { InstrumentCategory } from '../../types/api.ts'

const category = {
  key: 'baseStation',
  selectedModelId: 'uxm',
  connection: {
    endpoint: '192.168.1.112',
    controller: 'socket',
    notes: 'active UXM',
    connection_params: { timeout_ms: 30000 },
    base_station_model_presets: {
      uxm: {
        schema_version: 1,
        model_id: 'uxm',
        endpoint: '192.168.1.112',
        controller: 'socket',
        notes: 'saved UXM',
        connection_params: { timeout_ms: 30000 },
        base_station_adapter_profile: null,
      },
      cmw: {
        schema_version: 1,
        model_id: 'cmw',
        endpoint: 'TCPIP0::192.168.0.149::hislip0::INSTR',
        controller: 'hislip',
        notes: 'saved CMW',
        connection_params: { timeout_ms: 30000 },
        base_station_adapter_profile: {
          schema_version: 1,
          adapter: 'cmw500',
          lte_2x2_internal_route: {
            pcc_bb_board: 'BB1',
            rx_connector: 'RF1C',
            rx_converter: 'RX1',
            tx1_connector: 'RF1O',
            tx1_converter: 'TX1',
            tx2_connector: 'RF2C',
            tx2_converter: 'TX2',
          },
        },
      },
    },
    cmw500_lte_2x2_formal_enabled: false,
    cmw500_lte_2x2_formal_updated_at: null,
    base_station_site_certification: null,
  },
  models: [
    { id: 'uxm', base_station_manifest: null },
    {
      id: 'cmw',
      base_station_manifest: {
        schema_version: 2,
        adapter_id: 'cmw500',
        model_name: 'CMW500',
        vendor: 'R&S',
        rats: ['lte'],
        capabilities: [],
        rat_capabilities: [],
        operations: [],
        config_fields: [],
        attach_stages: [],
        measurement: null,
        profile_requirement: 'required',
        profile_schema_version: 1,
        profile_fields: [
          { path: 'lte_2x2_internal_route.pcc_bb_board', label: 'BB', required: true },
        ],
        manual_sources: [],
        diagnostic_supported: true,
        formal_gate: 'site_certification',
      },
    },
  ],
} as unknown as InstrumentCategory

test('model switch restores only the selected model saved preset', () => {
  const cmw = draftForBaseStationModel(category, 'cmw')
  assert.equal(cmw.endpoint, 'TCPIP0::192.168.0.149::hislip0::INSTR')
  assert.equal(cmw.notes, 'saved CMW')
  assert.equal(cmw.base_station_profile?.['lte_2x2_internal_route.pcc_bb_board'], 'BB1')

  const unknown = draftForBaseStationModel(category, 'new-model')
  assert.deepEqual(unknown, {
    modelId: 'new-model',
    endpoint: '',
    controller: '',
    notes: '',
    connection_params: '',
    base_station_profile: undefined,
  })
})

test('BaseStation model selection is draft-only and save carries modelId', () => {
  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
  const modelHandler = app.slice(
    app.indexOf('const handleModelChange'),
    app.indexOf('const handleFieldChange'),
  )
  assert.match(modelHandler, /categoryKey === 'baseStation'/)
  assert.match(modelHandler, /draftForBaseStationModel/)
  assert.match(modelHandler, /return\s*$/m)

  const saveHandler = app.slice(
    app.indexOf('const handleSaveConnection'),
    app.indexOf('const modelSelectData'),
  )
  assert.match(saveHandler, /categoryKey === 'baseStation'.*\? \{ modelId: draft\.modelId \}/s)
})

test('BaseStation save submits cleared fields instead of silently keeping the old preset', () => {
  assert.deepEqual(
    explicitBaseStationConnectionDraft(
      {
        modelId: 'uxm',
        endpoint: '',
        controller: '',
        notes: '',
        connection_params: '',
      },
      {},
      null,
    ),
    {
      endpoint: '',
      controller: '',
      notes: '',
      connection_params: {},
      base_station_adapter_profile: null,
    },
  )

  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
  const saveHandler = app.slice(
    app.indexOf('const handleSaveConnection'),
    app.indexOf('const modelSelectData'),
  )
  assert.match(saveHandler, /explicitBaseStationConnectionDraft\(/)
})
