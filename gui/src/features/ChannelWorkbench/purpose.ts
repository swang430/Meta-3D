export const candidates=['independent-24','independent-26','independent-31','shared-24','shared-26','shared-31']
export const ascCandidates=[...candidates,'existing-asc']
export type PurposeParameters={selection_start:number;selection_end:number;holdout_start:number;holdout_end:number|null;tap_budget_max:number;matrix_nmse_p95_max:number;phase_error_p95_max_deg:number;objective:string;mode:string;manual_candidate:string}
export function purposeParameters(p:PurposeParameters,hasAsc=false) {
 const frames=[p.selection_start,p.selection_end,p.holdout_start,...(p.holdout_end===null?[]:[p.holdout_end])]
 if(!frames.every(v=>Number.isInteger(v)&&v>=0)||p.selection_start>p.selection_end||(p.holdout_end!==null&&p.holdout_start>p.holdout_end)||p.holdout_start!==p.selection_end+1) throw Error('选择集与留出集须为非空、相邻且不重叠的连续源帧区间。')
 if(!Number.isInteger(p.tap_budget_max)||p.tap_budget_max<1||p.tap_budget_max>31||!Number.isFinite(p.matrix_nmse_p95_max)||p.matrix_nmse_p95_max<0||!Number.isFinite(p.phase_error_p95_max_deg)||p.phase_error_p95_max_deg<0||p.phase_error_p95_max_deg>180) throw Error('预算须为 1–31 的整数，矩阵阈值须非负，相位阈值须在 0–180 度。')
 if(!['phase','matrix'].includes(p.objective)||!['conducted','ota'].includes(p.mode)||(p.manual_candidate!==''&&!(hasAsc?ascCandidates:candidates).includes(p.manual_candidate))) throw Error('目标、模式或人工候选无效。')
 return p
}
export type Worst={frame_id:number;offset_hz:number;value:number;port_pair?:number[]}
export type Metric={valid:number;total:number;coverage:number|null;p95:number|null;worst:Worst|null}
export type Statistics={frames:number[];missing_frames:number[];actual_taps_min:number|null;actual_taps_max:number|null;matrix_nmse:Metric;phase_error_deg:Metric;constraints_met:boolean;changes_against_same_strategy_baseline:unknown}
export type Evaluation={schema:string;status:string;plan:Record<string,unknown>;provenance:Record<string,unknown>;selection:Record<string,Statistics>;selected_candidate:string|null;holdout:Statistics|null;manual_candidate:string|null;manual_holdout:Statistics|null;unmatched_frame_review?:Statistics|null;plan_fingerprint:string;selection_fingerprint:string;selection_input_fingerprint:string;automatic_adoption:false;formal_verdict:null;alignment_status:'unverified';ota_status:string;threshold_scope?:string;asc_comparison?:unknown;[key:string]:unknown}
export type Purpose={schema:string;status:string;formal_verdict:null;hardware_verified:false;alignment_status:'unverified';simulated:false;evaluation:Evaluation;frame_ids:number[];source_frame_count:number;download_url:string;points_url:string;source?:unknown;[key:string]:unknown}
export function readPurpose(raw:unknown):Purpose {
 const r=raw as Purpose,e=r?.evaluation
 if(!r||r.schema!=='mpdb-purpose/1'||!['selected','no_candidate_meets_constraints'].includes(r.status)||r.formal_verdict!==null||r.hardware_verified!==false||r.alignment_status!=='unverified'||r.simulated!==false||!e||e.schema!=='candidate-evaluation/1'||e.status!==r.status||e.formal_verdict!==null||e.alignment_status!=='unverified'||e.automatic_adoption!==false||!['not_evaluated','unverified'].includes(e.ota_status)||!e.selection||!e.plan||!e.provenance||!Array.isArray(r.frame_ids)||!Number.isInteger(r.source_frame_count)) throw Error('结果缺少证据或状态不符合离线分析约定。')
 const hasAsc=Object.hasOwn(e.candidate_parameters??{},'existing-asc')
 const expected=hasAsc?ascCandidates:candidates
 const sameKeys=(value:unknown)=>!!value&&typeof value==='object'&&Object.keys(value).sort().join(',')===[...expected].sort().join(',')
 if(!sameKeys(e.candidate_parameters)||!sameKeys(e.selection)) throw Error('结果须完整包含六个固定成员候选，上传 ASC 时须包含第七个候选。')
 if(hasAsc&&(typeof e.provenance.asc_sha256!=='string'||!/^[a-f0-9]{64}$/.test(e.provenance.asc_sha256))) throw Error('ASC 候选缺少来源哈希。')
 const validIds=(v:unknown):v is number[]=>Array.isArray(v)&&v.every((f,i)=>Number.isInteger(f)&&f>=0&&(i===0||f>v[i-1]))
 const reference=e.provenance.existing_asc_reference as {applicable_frames?:unknown}|undefined
 if(!validIds(r.frame_ids)||r.frame_ids.length!==r.source_frame_count||!validIds(r.common_frame_ids)||(hasAsc&&!validIds(reference?.applicable_frames))) throw Error('来源或共同源帧范围无效。')
 const recovered=hasAsc?new Set(reference!.applicable_frames as number[]):new Set(r.frame_ids)
 const common=r.frame_ids.filter(f=>recovered.has(f))
 if(common.length!==r.common_frame_ids.length||common.some((f,i)=>f!==(r.common_frame_ids as number[])[i])) throw Error('共同源帧须符合实际来源与 ASC 恢复帧的交集。')
 if(![e.plan_fingerprint,e.selection_fingerprint,e.selection_input_fingerprint].every(s=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s))) throw Error('结果缺少冻结指纹。')
 if(r.status==='no_candidate_meets_constraints'&&(e.selected_candidate!==null||e.holdout!==null)) throw Error('无候选达标时不得展示建议或建议留出。')
 if(r.status==='selected'&&(!expected.includes(e.selected_candidate??'')||!e.holdout)) throw Error('建议结果缺少独立留出。')
 if(e.manual_candidate!==null&&!expected.includes(e.manual_candidate)) throw Error('人工候选无效。')
 for(const [url,file] of [[r.download_url,'report.zip'],[r.points_url,'points.csv']]) if(typeof url!=='string'||!new RegExp('^/api/v1/channel-assets/mpdb-projects/purpose-evaluations/[a-zA-Z0-9-]+/'+file.replace('.','\\.')+'$').test(url)) throw Error('下载地址不符合约定。')
 return r
}

export function frameRange(value:unknown):string {return Array.isArray(value)&&value.length?`${value[0]}–${value[value.length-1]}`:'无'}
