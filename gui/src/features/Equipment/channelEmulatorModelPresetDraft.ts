/**
 * P2-58 ②：信道仿真器分型号 saved preset 的前端草稿（镜像 `baseStationModelPresetDraft.ts`）。
 *
 * 有意差别：
 * - **没有** adapter_profile 槽（CE 无 profile 层）；`alignment_name` /
 *   `available_channel_models` 等都是 `connection_params` 里的普通键，preset 原样带着，
 *   切型号时随 preset 一起还原（§6-① 按实测定：`alignment_name` 只被 F64 驱动读，算型号配置）。
 * - 切型号**先确认再换草稿**（用户拍板 ③）：有未保存草稿 → 弹确认；取消 → 草稿与型号都不变；
 *   确认 → 换成目标型号的 preset。BS 今天没有这道确认（Discovered-4，越界不补）。
 * - 切型号**不发任何请求**：后端 CE 块对只带 `modelId` 的 PUT 返回 422（model 与 connection
 *   必须一起保存），所以 model 只在「保存」时随 connection 一起发。
 *   这里的 effects 刻意只给 `applyDraft` / `confirmDiscard` 两个口，没有能发请求的口。
 */
import type {
  InstrumentCategory,
  InstrumentConnectionUpdate,
} from '../../types/api.ts'

export type SavedChannelEmulatorDraft = {
  modelId: string
  endpoint: string
  controller: string
  notes: string
  connection_params: string
}

/** App.tsx 的 EquipmentDraft 在本模块眼里的样子（connection_params 可缺省 = 空）。 */
export type ChannelEmulatorDraftLike = {
  modelId: string
  endpoint: string
  controller: string
  notes: string
  connection_params?: string
}

export function explicitChannelEmulatorConnectionDraft(
  draft: Pick<SavedChannelEmulatorDraft, 'endpoint' | 'controller' | 'notes'>,
  connectionParams: Record<string, unknown>,
): InstrumentConnectionUpdate {
  // 字段全部显式发出（含清空后的 ''），清空才会真的落库而不是被服务端回退到旧 preset。
  // 不带 base_station_adapter_profile 键：CE 块见到它就 422。
  return {
    endpoint: draft.endpoint,
    controller: draft.controller,
    notes: draft.notes,
    connection_params: connectionParams,
  }
}

const serializeParams = (params: Record<string, unknown> | null | undefined): string =>
  params && Object.keys(params).length > 0 ? JSON.stringify(params, null, 2) : ''

export function draftForChannelEmulatorModel(
  category: InstrumentCategory,
  modelId: string,
): SavedChannelEmulatorDraft {
  const preset = category.connection.channel_emulator_model_presets?.[modelId]
  if (!preset) {
    return { modelId, endpoint: '', controller: '', notes: '', connection_params: '' }
  }
  return {
    modelId,
    endpoint: preset.endpoint,
    controller: preset.controller,
    notes: preset.notes,
    connection_params: serializeParams(preset.connection_params),
  }
}

/**
 * 抽屉打开 / 保存成功后草稿的初值：活动型号取活动连接（与 App.tsx 初始化草稿的来源一致），
 * 其它型号取它的 saved preset。「有没有未保存草稿」就是跟这个基线比。
 */
export function savedChannelEmulatorDraft(
  category: InstrumentCategory,
  modelId: string,
): SavedChannelEmulatorDraft {
  if (modelId && modelId === (category.selectedModelId ?? '')) {
    return {
      modelId,
      endpoint: category.connection.endpoint ?? '',
      controller: category.connection.controller ?? '',
      notes: category.connection.notes ?? '',
      connection_params: serializeParams(category.connection.connection_params),
    }
  }
  return draftForChannelEmulatorModel(category, modelId)
}

// connection_params 是 JSON 文本；键序 / 空白不同不算改动，解析失败才退回原文比较。
const canonicalJson = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value) ?? 'undefined'
}

const isEmptyObject = (value: unknown): boolean =>
  value !== null && typeof value === 'object' && !Array.isArray(value) && Object.keys(value as object).length === 0

const canonicalParamsText = (text: string | undefined): string => {
  const raw = (text ?? '').trim()
  if (!raw) return ''
  try {
    const parsed: unknown = JSON.parse(raw)
    // 空对象与空文本同义：活动连接的 connection_params 为 {} 时 App.tsx 按真值序列化成 '{}'，
    // 而 serializeParams 给的基线是 ''；不归一就会在一次编辑都没做时误弹「丢弃未保存的配置」。
    return isEmptyObject(parsed) ? '' : canonicalJson(parsed)
  } catch {
    return raw
  }
}

export function hasUnsavedChannelEmulatorDraft(
  category: InstrumentCategory,
  draft: ChannelEmulatorDraftLike,
): boolean {
  const saved = savedChannelEmulatorDraft(category, draft.modelId)
  return (
    draft.endpoint !== saved.endpoint
    || draft.controller !== saved.controller
    || draft.notes !== saved.notes
    || canonicalParamsText(draft.connection_params) !== canonicalParamsText(saved.connection_params)
  )
}

export type ChannelEmulatorModelSwitchPlan =
  | { kind: 'noop' }
  | { kind: 'apply'; draft: SavedChannelEmulatorDraft }
  | { kind: 'confirm'; draft: SavedChannelEmulatorDraft }

export function planChannelEmulatorModelSwitch(
  category: InstrumentCategory,
  current: ChannelEmulatorDraftLike | undefined,
  modelId: string,
): ChannelEmulatorModelSwitchPlan {
  if (!modelId || (current && current.modelId === modelId)) return { kind: 'noop' }
  const next = draftForChannelEmulatorModel(category, modelId)
  if (current && hasUnsavedChannelEmulatorDraft(category, current)) {
    return { kind: 'confirm', draft: next }
  }
  return { kind: 'apply', draft: next }
}

export type ChannelEmulatorModelSwitchEffects = {
  /** 把草稿换成目标型号的 preset（唯一会改状态的口）。 */
  applyDraft: (draft: SavedChannelEmulatorDraft) => void
  /** 弹确认；只有操作员确认时才调用 `apply`，取消什么都不做。 */
  confirmDiscard: (apply: () => void) => void
}

export function switchChannelEmulatorModel(
  category: InstrumentCategory,
  current: ChannelEmulatorDraftLike | undefined,
  modelId: string,
  effects: ChannelEmulatorModelSwitchEffects,
): ChannelEmulatorModelSwitchPlan {
  const plan = planChannelEmulatorModelSwitch(category, current, modelId)
  if (plan.kind === 'apply') {
    effects.applyDraft(plan.draft)
  } else if (plan.kind === 'confirm') {
    effects.confirmDiscard(() => effects.applyDraft(plan.draft))
  }
  return plan
}
