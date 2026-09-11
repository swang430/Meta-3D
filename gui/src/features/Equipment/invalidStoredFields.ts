/**
 * P2-68：服务器把无法解析的存储字段标进 `connection.invalid_fields`（字段 → 原因）。
 * 这里是 GUI 侧的两条纯逻辑，都来自 Codex #471 R1：
 * - ① 每个字段给操作员的提示要**区分**「影响正式资格」（两个现场认证）与「只影响草稿 / 参数投影」
 *   （两个 preset map、connection_params）——正式门 `freeze_*` 不读 preset，不能一概说成"不能得到正式资格"（P2）。
 * - ③ 草稿带三态来源（server / invalid / operator），见下方 `ConnectionParamsOrigin`。
 * - ② 普通保存不得把被标坏的 `connection_params` 的**空草稿**当成 `{}` 发出去：抽屉对 BS / CE 一向显式发全字段，
 *   而库里的坏值一旦是 `dict()` 能转换的形态（如 `[["k","v"]]`），服务器就会接受 `{}` 并覆盖原值、还按 P2-72
 *   用空配置激活 HAL（P1）。收窄为：草稿不是 operator 来源（操作员没改过）时不发送它（BS 的 profile 兄弟键一起）——
 *   服务器对 dict() 可转换的坏形态会按已保存 preset 回填或写回 dict 化的原值，对其它坏形态在投影前就 500（什么都不写）；
 *   两种结果都不是「用 {} 覆盖」。
 */
export type InvalidStoredFields = Record<string, string>

export const INVALID_STORED_FIELD_HINTS: Record<string, string> = {
  base_station_site_certification:
    '基站现场认证无法解析：正式执行不能获得资格；用「从执行证据认证现场」重新认证即可覆盖。',
  channel_emulator_site_certification:
    '信道仿真器现场认证无法解析：正式执行不能获得资格；重新认证即可覆盖。',
  base_station_model_presets:
    '基站各型号的已保存配置草稿无法解析，抽屉按空草稿显示；不影响现场认证与正式资格。服务器会拒绝对该品类的保存，需管理员修复数据库。',
  channel_emulator_model_presets:
    '信道仿真器各型号的已保存配置草稿无法解析，抽屉按空草稿显示；不影响现场认证与正式资格。服务器会拒绝对该品类的保存，需管理员修复数据库。',
  connection_params:
    '连接参数无法解析，已按空显示；普通保存不再把空草稿当作新值发送，但该品类的保存仍可能被服务器拒绝（500），需管理员修复数据库。',
}

export function invalidStoredFieldHint(field: string): string {
  return INVALID_STORED_FIELD_HINTS[field] ?? '该字段无法解析，已按「不可用」显示。'
}

/**
 * 草稿里 connection_params 文本的来源（Codex #471 R2/R3 + 用户 2026-09-11 拍板 A）：
 * - 'server'   = 从**有效**的服务器值灌入、操作员未动；
 * - 'invalid'  = 服务器把该字段标坏时初始化，文本恒为空 —— 空不代表操作员想清空；
 * - 'operator' = 操作员改过（rfSwitch JsonInput / CE alignment 输入 / BS profile 字段 / 切型号选 preset）—— 填了照发。
 * BS 的 profile 草稿从同一个存储字段派生，与文本共用这份来源：行变坏时一起清空、修好时一起重建、被守卫时一起不发。
 */
export type ConnectionParamsOrigin = 'server' | 'invalid' | 'operator'

export type ConnectionParamsDraft = { text: string; origin: ConnectionParamsOrigin }

/** 当前草稿的 connection_params 能不能被拿去保存（也决定 CE alignment 输入框是否禁用）。 */
export function connectionParamsGuarded(
  invalidFields: InvalidStoredFields | undefined,
  draftOrigin: ConnectionParamsOrigin | undefined,
): boolean {
  const origin = draftOrigin ?? 'server'
  if (origin === 'invalid') return true
  const markerPresent = invalidFields !== undefined && 'connection_params' in invalidFields
  // 服务器仍标坏：只有操作员明确改过的文本可以发；从服务器灌入的（可能已陈旧的）文本不可信（Codex #471 R3 P1）
  return markerPresent && origin !== 'operator'
}

/**
 * 被守卫时，从保存 payload 里去掉 connection_params **和**从同一存储字段拆出去的 BS
 * `base_station_adapter_profile`（它在库里就是 connection_params.base_station_adapter_profile，
 * 草稿同样是从服务器灌入派生的 —— 轻量内审 R3-F1），交给服务器按已保存 preset / 活动连接回填；
 * 其它情况 payload 原样返回，保持 BS / CE "显式发全字段、清空才真清空" 的既有语义。
 */
export function withoutSynthesizedConnectionParams<
  T extends { connection_params?: unknown; base_station_adapter_profile?: unknown },
>(
  payload: T,
  invalidFields: InvalidStoredFields | undefined,
  draftOrigin: ConnectionParamsOrigin | undefined,
): T {
  if (!connectionParamsGuarded(invalidFields, draftOrigin)) return payload
  const rest = { ...payload }
  delete rest.connection_params
  delete rest.base_station_adapter_profile
  return rest
}

/**
 * 目录每次刷新时算下一份 connection_params 草稿：
 * - 服务器标坏：'operator' 来源保留（操作员的输入不丢）；'server' / 'invalid' / 无草稿 → 清空并记 'invalid'
 *   （服务器说它坏了，之前从服务器灌入的旧文本不可信 —— R3 P1）；
 * - 服务器有效：'invalid' → 用修好的服务器值重建（rehydrate，R2 P1）；'server' / 'operator' → 沿用（不重刷未保存的编辑）；
 *   无草稿 → 取服务器值。
 * 切型号选 preset 由调用方标成 'operator'，所以修好后不会被活动型号的参数跨型号重建（轻量内审 F2）。
 */
export function nextConnectionParamsDraft(
  previous: ConnectionParamsDraft | undefined,
  server: { text: string; invalid: boolean },
): ConnectionParamsDraft {
  if (server.invalid) {
    if (previous?.origin === 'operator') return previous
    return { text: '', origin: 'invalid' }
  }
  if (!previous || previous.origin === 'invalid') return { text: server.text, origin: 'server' }
  return previous
}
