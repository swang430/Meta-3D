import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  draftForChannelEmulatorModel,
  explicitChannelEmulatorConnectionDraft,
  hasUnsavedChannelEmulatorDraft,
  planChannelEmulatorModelSwitch,
  savedChannelEmulatorDraft,
  switchChannelEmulatorModel,
  type ChannelEmulatorModelSwitchEffects,
  type SavedChannelEmulatorDraft,
} from './channelEmulatorModelPresetDraft.ts'
import type { InstrumentCategory } from '../../types/api.ts'

// 活动 F64 连接的参数：全是操作员 / 同步维护的型号配置资产，preset 必须原样带着。
const f64Params = {
  timeout_sec: 30,
  alignment_name: 'CAICT_2026-08_n78',
  available_channel_models: [
    { filename: '3GPP_5GNR_1x1_TDLA30-5.smu', radio_technology: 'nr5g' },
    'New GCM Model 5.smu',
  ],
  default_emulation_file: 'New GCM Model 5.smu',
}

const category = {
  key: 'channelEmulator',
  selectedModelId: 'f64',
  connection: {
    id: 'conn-ce',
    endpoint: '192.168.100.21:3334',
    controller: 'socket',
    notes: 'active F64',
    connection_params: f64Params,
    channel_emulator_model_presets: {
      f64: {
        schema_version: 1,
        model_id: 'f64',
        endpoint: '192.168.100.21:3334',
        controller: 'socket',
        notes: 'active F64',
        connection_params: f64Params,
      },
      fs16: {
        schema_version: 1,
        model_id: 'fs16',
        endpoint: 'TCPIP0::192.168.100.22::inst0::INSTR',
        controller: 'visa',
        notes: 'saved FS16',
        connection_params: {},
      },
    },
    cmw500_lte_2x2_formal_enabled: false,
    cmw500_lte_2x2_formal_updated_at: null,
    base_station_site_certification: null,
  },
  models: [{ id: 'f64' }, { id: 'fs16' }, { id: 'new-model' }],
} as unknown as InstrumentCategory

const readApp = () => readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8')
const modelHandlerOf = (app: string) =>
  app.slice(app.indexOf('const handleModelChange'), app.indexOf('const handleFieldChange'))
const saveHandlerOf = (app: string) =>
  app.slice(app.indexOf('const handleSaveConnection'), app.indexOf('const modelSelectData'))
const channelEmulatorBranchOf = (modelHandler: string) => {
  const start = modelHandler.indexOf("categoryKey === 'channelEmulator' && category")
  const end = modelHandler.indexOf('setDrafts((prev) => {\n        const current', start)
  assert.ok(start > 0, 'handleModelChange has no channelEmulator branch')
  assert.ok(end > start, 'channelEmulator branch is not followed by the generic path')
  return modelHandler.slice(start, end)
}

// 记录型 effects：只有 applyDraft / confirmDiscard 两个口，取消 = 不调用捕获到的 apply。
function recordingEffects() {
  const ops: string[] = []
  const applied: SavedChannelEmulatorDraft[] = []
  let pendingApply: (() => void) | undefined
  const effects: ChannelEmulatorModelSwitchEffects = {
    applyDraft: (draft) => {
      ops.push('applyDraft')
      applied.push(draft)
    },
    confirmDiscard: (apply) => {
      ops.push('confirmDiscard')
      pendingApply = apply
    },
  }
  const confirm = () => {
    assert.ok(pendingApply, 'no confirm dialog is pending')
    const run = pendingApply
    pendingApply = undefined
    run?.()
  }
  return { effects, ops, applied, confirm }
}

test('model switch restores the selected model saved preset verbatim, unknown model gets an empty draft', () => {
  const f64 = draftForChannelEmulatorModel(category, 'f64')
  assert.equal(f64.endpoint, '192.168.100.21:3334')
  assert.equal(f64.controller, 'socket')
  assert.equal(f64.notes, 'active F64')
  // alignment_name 与 available_channel_models 都随 preset 原样回来（§6-① 拍板：算）
  assert.deepEqual(JSON.parse(f64.connection_params), f64Params)

  const fs16 = draftForChannelEmulatorModel(category, 'fs16')
  assert.equal(fs16.endpoint, 'TCPIP0::192.168.100.22::inst0::INSTR')
  assert.equal(fs16.notes, 'saved FS16')
  assert.equal(fs16.connection_params, '')

  assert.deepEqual(draftForChannelEmulatorModel(category, 'new-model'), {
    modelId: 'new-model',
    endpoint: '',
    controller: '',
    notes: '',
    connection_params: '',
  })
})

test('unsaved detection: active model compares against the active connection, others against their preset; JSON key order is not a change', () => {
  const active = savedChannelEmulatorDraft(category, 'f64')
  assert.equal(hasUnsavedChannelEmulatorDraft(category, active), false)

  const reordered = {
    ...active,
    connection_params: JSON.stringify({
      default_emulation_file: 'New GCM Model 5.smu',
      available_channel_models: f64Params.available_channel_models,
      alignment_name: 'CAICT_2026-08_n78',
      timeout_sec: 30,
    }),
  }
  assert.equal(hasUnsavedChannelEmulatorDraft(category, reordered), false)

  const alignmentEdited = {
    ...active,
    connection_params: JSON.stringify({ ...f64Params, alignment_name: 'EDITED' }, null, 2),
  }
  assert.equal(hasUnsavedChannelEmulatorDraft(category, alignmentEdited), true)
  assert.equal(hasUnsavedChannelEmulatorDraft(category, { ...active, notes: 'typed' }), true)

  const fs16 = draftForChannelEmulatorModel(category, 'fs16')
  assert.equal(hasUnsavedChannelEmulatorDraft(category, fs16), false)
  assert.equal(
    hasUnsavedChannelEmulatorDraft(category, { ...fs16, endpoint: 'TCPIP0::10.0.0.1::inst0::INSTR' }),
    true,
  )

  // 活动连接与它的 preset 漂移（smu-sync 等带外写）时，基线仍是抽屉加载的活动连接，不误报
  const drifted = {
    ...category,
    connection: { ...category.connection, notes: 'edited out of band' },
  } as InstrumentCategory
  assert.equal(hasUnsavedChannelEmulatorDraft(drifted, savedChannelEmulatorDraft(drifted, 'f64')), false)
})

test('an active connection whose connection_params is {} is not an unsaved draft, so the first switch applies without a confirm', () => {
  // 内审 F2：任一型号用空参数保存后，活动连接的 connection_params 是 {}（不是 null）。
  // App.tsx 初始化草稿按真值序列化 → '{}'，而 savedChannelEmulatorDraft 的基线是 ''；两端必须比成相等，
  // 否则一次编辑都没做就切型号会误弹「丢弃未保存的配置」。
  const emptyActive = {
    ...category,
    connection: { ...category.connection, connection_params: {} },
  } as InstrumentCategory
  const appDraft = { ...savedChannelEmulatorDraft(emptyActive, 'f64'), connection_params: '{}' }
  assert.equal(hasUnsavedChannelEmulatorDraft(emptyActive, appDraft), false)
  assert.equal(planChannelEmulatorModelSwitch(emptyActive, appDraft, 'fs16').kind, 'apply')
  // 带空白 / 换行的空对象同样不算改动；真有键才算
  assert.equal(hasUnsavedChannelEmulatorDraft(emptyActive, { ...appDraft, connection_params: ' {\n}\n' }), false)
  assert.equal(
    hasUnsavedChannelEmulatorDraft(emptyActive, { ...appDraft, connection_params: '{"timeout_sec": 10}' }),
    true,
  )
})

test('switching with an unsaved draft asks first; cancel keeps draft and model, confirm swaps in the target preset', () => {
  const edited = {
    ...savedChannelEmulatorDraft(category, 'f64'),
    connection_params: JSON.stringify({ ...f64Params, alignment_name: 'EDITED' }),
  }
  const rec = recordingEffects()
  const plan = switchChannelEmulatorModel(category, edited, 'fs16', rec.effects)
  assert.equal(plan.kind, 'confirm')
  assert.deepEqual(rec.ops, ['confirmDiscard'])
  // 取消 = 不调 apply：没有任何草稿被换，型号也没变
  assert.deepEqual(rec.applied, [])

  rec.confirm()
  assert.deepEqual(rec.applied, [draftForChannelEmulatorModel(category, 'fs16')])
  assert.equal(rec.applied[0].modelId, 'fs16')
})

test('switching without unsaved changes applies immediately, same model is a no-op, switching back restores the F64 preset', () => {
  const rec = recordingEffects()
  const toFs16 = switchChannelEmulatorModel(
    category,
    savedChannelEmulatorDraft(category, 'f64'),
    'fs16',
    rec.effects,
  )
  assert.equal(toFs16.kind, 'apply')
  assert.deepEqual(rec.ops, ['applyDraft'])
  assert.equal(rec.applied[0].endpoint, 'TCPIP0::192.168.100.22::inst0::INSTR')

  const backToF64 = switchChannelEmulatorModel(category, rec.applied[0], 'f64', rec.effects)
  assert.equal(backToF64.kind, 'apply')
  assert.deepEqual(JSON.parse(rec.applied[1].connection_params), f64Params)

  const same = switchChannelEmulatorModel(category, rec.applied[1], 'f64', rec.effects)
  assert.equal(same.kind, 'noop')
  assert.deepEqual(rec.ops, ['applyDraft', 'applyDraft'])

  assert.equal(planChannelEmulatorModelSwitch(category, undefined, 'fs16').kind, 'apply')
  assert.equal(planChannelEmulatorModelSwitch(category, rec.applied[1], '').kind, 'noop')
})

test('model switch never issues a request: effects have no request-capable op and the App branch returns before any mutate', () => {
  const rec = recordingEffects()
  switchChannelEmulatorModel(
    category,
    { ...savedChannelEmulatorDraft(category, 'f64'), notes: 'dirty' },
    'fs16',
    rec.effects,
  )
  rec.confirm()
  switchChannelEmulatorModel(category, rec.applied[0], 'f64', rec.effects)
  assert.deepEqual([...new Set(rec.ops)].sort(), ['applyDraft', 'confirmDiscard'])
  assert.deepEqual(Object.keys(rec.effects).sort(), ['applyDraft', 'confirmDiscard'])

  const branch = channelEmulatorBranchOf(modelHandlerOf(readApp()))
  assert.match(branch, /switchChannelEmulatorModel\(category, drafts\[categoryKey\], modelId,/)
  assert.match(branch, /\breturn\b/)
  // 后端 CE 块对只带 modelId 的 PUT 返回 422：这个分支里不许出现任何发请求的东西
  assert.doesNotMatch(branch, /mutate\(|updateInstrumentCategory\(|client\.|\.put\(|payload/)
})

test('the confirm is the Mantine confirm modal and only its confirm button applies the swap', () => {
  const branch = channelEmulatorBranchOf(modelHandlerOf(readApp()))
  assert.match(branch, /confirmDiscard: \(apply\) => modals\.openConfirmModal\(\{/)
  assert.match(branch, /onConfirm: apply,/)
  assert.match(branch, /labels: \{ confirm: '丢弃并切换', cancel: '取消' \}/)
  assert.match(branch, /applyDraft: \(next\) => setDrafts\(\(prev\) => \(\{ \.\.\.prev, \[categoryKey\]: next \}\)\)/)
})

test('channelEmulator save carries modelId together with the explicit connection draft', () => {
  const saveHandler = saveHandlerOf(readApp())
  assert.match(
    saveHandler,
    /categoryKey === 'baseStation' \|\| categoryKey === 'channelEmulator'\s*\? \{ modelId: draft\.modelId \}/,
  )
  assert.match(
    saveHandler,
    /categoryKey === 'channelEmulator'\s*\? explicitChannelEmulatorConnectionDraft\(draft, parsedParams \?\? \{\}\)/,
  )
  assert.match(
    saveHandler,
    /categoryKey === 'baseStation' \|\| categoryKey === 'channelEmulator' \? \{\} : undefined/,
  )

  // 清空的字段显式发出，服务端才不会回退到旧 preset；不带 base_station_adapter_profile（CE 块见到就 422）
  const cleared = explicitChannelEmulatorConnectionDraft(
    { endpoint: '', controller: '', notes: '' },
    {},
  )
  assert.deepEqual(cleared, { endpoint: '', controller: '', notes: '', connection_params: {} })
  assert.equal('base_station_adapter_profile' in cleared, false)
  assert.deepEqual(
    explicitChannelEmulatorConnectionDraft(
      { endpoint: '192.168.100.21:3334', controller: 'socket', notes: 'n' },
      f64Params,
    ).connection_params,
    f64Params,
  )
})

test('lab profile service and the drawer alignment field consume the channelEmulator truth', () => {
  const service = readFileSync(new URL('../../api/labProfileService.ts', import.meta.url), 'utf8')
  assert.match(service, /export async function fetchChannelEmulatorBindingPreview\(/)
  assert.match(service, /Promise<ChannelEmulatorBindingPreviewResponse>/)
  assert.match(service, /instrument-bindings\/channelEmulator\/preview/)

  // alignment 字段读的是草稿 connection_params —— 切型号换草稿后它随 preset 一起变
  const app = readApp()
  const drawer = app.slice(
    app.indexOf("category.key === 'channelEmulator' && (() => {"),
    app.indexOf('<ChannelModelsCard categoryKey={category.key} />'),
  )
  assert.ok(drawer.length > 0)
  assert.match(drawer, /draft\.connection_params/)
  assert.match(drawer, /parsedParams\.alignment_name/)
  assert.match(drawer, /label="F64 User Alignment 文件名"/)
})
