export type BudgetRow = {tap_budget:number;used_taps_min:number;used_taps_max:number;matrix_nmse_median:number|null;matrix_nmse_p95:number|null;phase_error_p95_deg:number|null;common_valid:number;improved:number;worse:number;unchanged:number}
export type Budget = {schema:string;status:string;alignment_status:string;formal_verdict:null;simulated:false;hardware_verified:false;source_frame_count:number;frame_ids:number[];tap_budgets:number[];strategies:string[];summary:Record<string,BudgetRow>;download_url:string;points_url:string;source:Record<string,string>;mpdb_sha256:string;port_order:unknown;port_pairs:unknown;offsets_hz:number[];amplitude_floor:number}
export function budgetLink(value:string) {
 if (typeof value !== 'string' || !/^\/api\/v1\/channel-assets\/mpdb-projects\/budget-comparisons\/[a-zA-Z0-9-]+\/(report\.zip|points\.csv)$/.test(value)) throw Error('下载地址无效。')
 return value
}
export function readBudget(value:Budget):Budget {
 const fail = () => { throw Error('预算比较结果缺少证据或状态不符合约定，无法展示。') }
 const count = (n:number) => Number.isInteger(n) && n >= 0
 if (!value || value.schema !== 'mpdb-budget/1' || value.status !== 'unverified' || value.alignment_status !== 'unverified' || value.formal_verdict !== null || value.simulated !== false || value.hardware_verified !== false || JSON.stringify(value.tap_budgets) !== '[24,26,31]' || JSON.stringify(value.strategies) !== '["independent","shared"]' || !count(value.source_frame_count) || value.source_frame_count < 1 || !Array.isArray(value.frame_ids) || value.frame_ids.length !== value.source_frame_count || new Set(value.frame_ids).size !== value.source_frame_count || !value.frame_ids.every(count) || !value.source || !/^[a-f0-9]{64}$/.test(value.source.archive) || !/^[a-f0-9]{64}$/.test(value.source.members) || !/^[a-f0-9]{64}$/.test(value.mpdb_sha256)) fail()
 for (const strategy of ['independent','shared']) for (const budget of [24,26,31]) {
  const r = value.summary?.[`${strategy}-${budget}`]
  if (!r || r.tap_budget !== budget || ![r.used_taps_min,r.used_taps_max,r.common_valid,r.improved,r.worse,r.unchanged].every(count) || r.used_taps_min > r.used_taps_max || r.used_taps_max > budget || r.improved+r.worse+r.unchanged !== r.common_valid || ![r.matrix_nmse_median,r.matrix_nmse_p95,r.phase_error_p95_deg].every(n => n === null || typeof n === 'number' && Number.isFinite(n) && n >= 0)) fail()
 }
 budgetLink(value.download_url); budgetLink(value.points_url)
 return value
}
