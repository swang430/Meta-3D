import type { BatchJobRecord, FixedRouteRecord, RouteApplicationRecord } from '../../types/api'

/** 只为显示关联已读取子记录；不从旧缓存、请求或其他批的同名项补数。 */
export function batchResultRecord(job: BatchJobRecord, item: BatchJobRecord['items'][number], records: FixedRouteRecord[]) {
  const record = records.find(row => row.run_id === item.run_id)
  const result = record?.result
  if (!record || !result || record.lab_profile_id !== job.lab_id || result.lab_profile_id !== job.lab_id ||
    result.run_id !== item.run_id || result.states?.batch_job_id !== job.job_id || result.states?.batch_item_id !== item.item_id ||
    record.batch_context?.job_id != null && record.batch_context.job_id !== job.job_id) return undefined
  return record
}

/** 采用历史不是当前有效性或认证证明。未读到历史不能说没有采用。 */
export function adoptionHistoryLabel(record: FixedRouteRecord, rows: RouteApplicationRecord[] | undefined) {
  if (!rows) return '采用记录尚未核对'
  return rows.some(row => row.acquisition_run_id === record.run_id && row.selection_snapshot.lab_profile_id === record.lab_profile_id)
    ? '已有确认采用记录；当前适用性及撤销状态另核' : '本页历史未见本次采集的采用记录'
}
