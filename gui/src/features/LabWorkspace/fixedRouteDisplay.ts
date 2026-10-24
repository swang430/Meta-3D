import type { FixedRouteRecord } from '../../types/api'

export const acquisitionStatus: Record<string, string> = {
  running: '正在采集', completed: '采集完成（未签发校准资格）', simulated: '模拟流程完成（无真实测量）',
  failed: '采集失败', cancelled: '已取消', cleanup_unconfirmed: '可能仍在发射：停止未确认',
  interrupted: '采集中断：停发状态需现场确认', incomplete: '记录不完整',
}

/** 只格式化服务器结果，不从请求设置值或当前配置计算功率。 */
export function fixedRouteDisplay(record: FixedRouteRecord) {
  const result = record.result
  const measured = record.status === 'completed' && result?.status === 'completed' && result.cleanup_confirmed === true
  const samples = measured ? result.samples ?? [] : []
  const last = samples.at(-1)
  const reading = (value: number | undefined | null) => typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)} dBm` : '无实测读数'
  const loss = measured ? result.net_loss_db : null
  return {
    label: acquisitionStatus[record.status] ?? '状态未知',
    source: reading(last?.source_after_dbm), received: reading(last?.received_dbm),
    loss: typeof loss === 'number' && Number.isFinite(loss) ? `${loss.toFixed(2)} dB（${loss < 0 ? '增益' : '损耗'}）` : '未计算',
  }
}
