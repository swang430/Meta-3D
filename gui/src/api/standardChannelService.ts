/**
 * Standard Channel Definition (SCD) — P2-12 slice 3 (A) 前端 service。
 *
 * 后端 REST: app/api/standard_channel.py (prefix /standard-channels, 挂 /api/v1)。
 * SCD 绑定到 channelEmulator 类别的 InstrumentConnection; associate 后更新该连接的
 * connection_params['available_channel_models'] (synced projection) —— 即 MIMO OTA
 * 配置里 emulation_file 下拉 (#120) 的数据源。
 *
 * 手写 service (不走 openapi generate, 跟 fetchChannelModels / topology profile 一致)。
 */
import client from './client'

/** 镜像后端 SCDResponse。standard_name 由后端从规范字段算 (单一真值, 不接受前端传)。 */
export interface StandardChannel {
  id: string
  radio_technology: 'nr5g' | 'lte'
  channel_kind: 'nr_arfcn' | 'lte_dl_earfcn'
  band: string
  arfcn: number | null
  lte_dl_earfcn: number | null
  bandwidth_mhz: number
  model: string
  scenario: string
  mimo: string
  polarization: string
  version: number
  standard_name: string
  instrument_connection_id: string
  associated_file_path: string | null
  association_source: string // declared_only | standard_generated | vendor_associated
  description: string | null
  created_at: string | null
  updated_at: string | null
}

/** 镜像后端 SCDCreateRequest。 */
export interface StandardChannelCreatePayload {
  instrument_connection_id: string
  radio_technology: 'nr5g' | 'lte'
  channel_kind: 'nr_arfcn' | 'lte_dl_earfcn'
  band: string
  arfcn?: number | null
  lte_dl_earfcn?: number | null
  bandwidth_mhz: number
  model: string
  scenario: string
  mimo: string
  polarization: string
  version?: number
  description?: string | null
}

/** 镜像后端 SCDAssociateRequest。 */
export interface StandardChannelAssociatePayload {
  file_path: string
  /**
   * standard_generated (路径 a/b: 文件按标准名生成, basename 须 == 标准名) |
   * vendor_associated (路径 c: 关联已有厂商文件, 仅频率 cross-check)。默认 vendor_associated。
   */
  association_source?: string
}

/** 列某台 F64 (channelEmulator connection) 的标准信道定义。 */
export const fetchStandardChannels = async (
  instrumentConnectionId: string,
): Promise<StandardChannel[]> => {
  const response = await client.get<StandardChannel[]>('/standard-channels', {
    params: { instrument_connection_id: instrumentConnectionId },
  })
  return response.data
}

/** 创建标准信道定义 (declared_only, 未关联文件)。字段非法/重复/绑定非法 → 400。 */
export const createStandardChannel = async (
  payload: StandardChannelCreatePayload,
): Promise<StandardChannel> => {
  const response = await client.post<StandardChannel>('/standard-channels', payload)
  return response.data
}

/** 关联实际 .smu 文件 → 更新 available_channel_models projection。cross-check 失败 → 400。 */
export const associateStandardChannelFile = async (
  scdId: string,
  payload: StandardChannelAssociatePayload,
): Promise<StandardChannel> => {
  const response = await client.post<StandardChannel>(
    `/standard-channels/${scdId}/associate`,
    payload,
  )
  return response.data
}

/** 删除 SCD (已关联则同步移除其 projection 条目)。 */
export const deleteStandardChannel = async (scdId: string): Promise<void> => {
  await client.delete(`/standard-channels/${scdId}`)
}
