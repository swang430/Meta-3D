import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  draftForBaseStationModel,
  explicitBaseStationConnectionDraft,
  hasUnsavedBaseStationSyncDraft,
  hasUnsavedInstrumentSyncDraft,
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

test('BaseStation save reports automatic category HAL activation without a manual reload reminder', () => {
  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
  const feedbackHelper = app.slice(
    app.indexOf('const showFeedback'),
    app.indexOf('const diagnosticTargetFor'),
  )
  assert.match(feedbackHelper, /durationMs\s*=\s*2000/)
  assert.match(feedbackHelper, /},\s*durationMs\)/)

  const saveMutation = app.slice(
    app.indexOf('const instrumentMutation'),
    app.indexOf('const siteCertificationMutation'),
  )
  assert.match(saveMutation, /HAL 尚未激活/)
  assert.doesNotMatch(saveMutation, /页面顶部「↻ 重新加载驱动」/)
  assert.match(
    saveMutation,
    /activationError[\s\S]*?12000/,
  )
})

test('UXM topology card is rendered only for the draft UXM adapter', () => {
  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
  assert.match(
    app,
    /drawerSelectedModel\?\.base_station_manifest\?\.adapter_id === ['"]uxm['"][\s\S]*?<TopologyProfileCard/,
  )
})

test('LabProfile sync stays blocked until the BaseStation draft is saved as the active configuration', () => {
  const savedActiveDraft = {
    modelId: 'uxm',
    endpoint: '192.168.1.112',
    controller: 'socket',
    notes: 'active UXM',
    connection_params: JSON.stringify({ timeout_ms: 30000 }),
  }

  assert.equal(hasUnsavedBaseStationSyncDraft(category, savedActiveDraft), false)
  assert.equal(
    hasUnsavedBaseStationSyncDraft(category, {
      ...savedActiveDraft,
      endpoint: '192.168.1.132',
    }),
    true,
  )
  // Even an exact CMW saved preset is still only a draft until modelId is saved active.
  assert.equal(
    hasUnsavedBaseStationSyncDraft(category, draftForBaseStationModel(category, 'cmw')),
    true,
  )
})

test('the equipment drawer makes Save precede Sync and disables Sync for every unsaved instrument draft', () => {
  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
  const drawer = app.slice(
    app.indexOf("const category = categories.find((c) => c.key === editingCategoryKey)"),
    app.indexOf('{/* ─── SCPI 命令终端 ─── */}'),
  )

  assert.match(drawer, /hasUnsavedInstrumentSyncDraft\(category, draft\)/)
  assert.match(drawer, /disabled=\{[\s\S]*?hasUnsavedSyncDraft[\s\S]*?\}/)
  assert.match(drawer, /请先保存配置，再同步/)
  assert.ok(
    drawer.indexOf('保存配置') < drawer.indexOf('同步已保存配置'),
    'Save must be shown before Sync so the visible workflow matches the server contract',
  )

  const saveLabel = drawer.indexOf('保存配置')
  const saveButton = drawer.slice(drawer.lastIndexOf('<Button', saveLabel), saveLabel)
  assert.match(saveButton, /disabled=\{syncLabBindingMutation\.isPending\}/)
})

test('every syncable instrument category blocks stale saved-state sync', () => {
  const genericCategory = {
    ...category,
    key: 'signalAnalyzer',
  } as InstrumentCategory
  const saved = {
    modelId: 'uxm',
    endpoint: '192.168.1.112',
    controller: 'socket',
    notes: 'active UXM',
    connection_params: JSON.stringify({ timeout_ms: 30000 }),
  }

  assert.equal(hasUnsavedInstrumentSyncDraft(genericCategory, saved), false)
  assert.equal(
    hasUnsavedInstrumentSyncDraft(genericCategory, {
      ...saved,
      endpoint: '192.168.1.132',
    }),
    true,
  )
  assert.equal(
    hasUnsavedInstrumentSyncDraft(genericCategory, { ...saved, modelId: 'cmw' }),
    true,
  )
})
