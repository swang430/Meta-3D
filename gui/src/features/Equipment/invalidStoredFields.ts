/**
 * P2-68：服务器把无法解析的存储字段标进 `connection.invalid_fields`（字段 → 原因）。
 * 这里是 GUI 侧的两条纯逻辑，都来自 Codex #471 R1：
 * - ① 每个字段给操作员的提示要**区分**「影响正式资格」（两个现场认证）与「只影响草稿 / 参数投影」
 *   （两个 preset map、connection_params）——正式门 `freeze_*` 不读 preset，不能一概说成"不能得到正式资格"（P2）。
 * - ② 普通保存不得把被标坏的 `connection_params` 的**空草稿**当成 `{}` 发出去：抽屉对 BS / CE 一向显式发全字段，
 *   而库里的坏值一旦是 `dict()` 能转换的形态（如 `[["k","v"]]`），服务器就会接受 `{}` 并覆盖原值、还按 P2-72
 *   用空配置激活 HAL（P1）。收窄为：该字段被标坏且操作员没填新 JSON 时，不发送它 —— 服务器对 dict() 可转换的坏形态
 *   会按已保存 preset 回填或写回 dict 化的原值，对其它坏形态在投影前就 500（什么都不写）；两种结果都不是「用 {} 覆盖」。
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
 * 被标坏的 connection_params + 空草稿 → 从保存 payload 里去掉该键；操作员真填了新 JSON 则原样发。
 * 其它情况（字段没被标坏）payload 原样返回，保持 BS / CE "显式发全字段、清空才真清空" 的既有语义。
 */
export function withoutSynthesizedConnectionParams<T extends { connection_params?: unknown }>(
  payload: T,
  invalidFields: InvalidStoredFields | undefined,
  draftParamsText: string | undefined,
  draftOrigin: ConnectionParamsOrigin | undefined = 'server',
): T {
  // 服务器仍标坏，或草稿还是无效来源、尚未用修好的值重建（Codex #471 R2 P1：标记消失≠草稿已刷新）
  const guarded = (invalidFields !== undefined && 'connection_params' in invalidFields) || draftOrigin === 'invalid'
  if (!guarded) return payload
  if ((draftParamsText ?? '').trim()) return payload
  const rest = { ...payload }
  delete rest.connection_params
  return rest
}

/** 草稿里 connection_params 文本的来源：'invalid' = 初始化时服务器把该字段标坏，空文本不代表操作员意图。 */
export type ConnectionParamsOrigin = 'server' | 'invalid'

export type ConnectionParamsDraft = { text: string; origin: ConnectionParamsOrigin }

/**
 * 目录每次刷新时算下一份 connection_params 草稿（Codex #471 R2 P1）：
 * - 服务器仍标坏：保留操作员可能已输入的文本（初值空）；首次看到坏值记 'invalid'，已有草稿保留自己的来源；
 * - 标记刚消失、草稿还是无效来源的未动空文本：用修好的服务器值重建（rehydrate），origin 回 'server'——
 *   否则管理员修库后、抽屉没关，下一次不相关的保存又会把空草稿当 {} 发出去覆盖修好的值；
 * - 其它：沿用旧草稿（未保存的编辑不丢），没有旧草稿就取服务器值。
 */
export function nextConnectionParamsDraft(
  previous: ConnectionParamsDraft | undefined,
  server: { text: string; invalid: boolean },
): ConnectionParamsDraft {
  // 只有首次看到坏值（还没有草稿）才记 'invalid'；已有草稿保留自己的来源 —— 切型号 / preset 产生的草稿是 'server'，
  // 修好后不能被活动型号的参数跨型号重建（轻量内审 F2）
  if (server.invalid) return { text: previous?.text ?? '', origin: previous?.origin ?? 'invalid' }
  if (previous?.origin === 'invalid' && !previous.text.trim()) return { text: server.text, origin: 'server' }
  return { text: previous?.text ?? server.text, origin: 'server' }
}
