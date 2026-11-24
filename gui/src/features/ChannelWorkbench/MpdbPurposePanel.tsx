import { useState, useRef, type FormEvent } from 'react'
import { Alert, Anchor, Button, Group, Stack, Table, Text, Title } from '@mantine/core'
import { isAxiosError } from 'axios'
import client from '../../api/client'
import { comparisonParameters, metric } from './comparison'
import { candidates, frameRange, purposeParameters, readPurpose, type Purpose, type Statistics, type Metric } from './purpose'
function MetricView({label,value}:{label:string;value:Metric}) {
 const w=value.worst
 return <Text>{label} P95：{metric(value.p95)}；覆盖率：{value.valid}/{value.total}（{metric(value.coverage)}）；最差点：{w?`帧 ${w.frame_id}，频偏 ${w.offset_hz} Hz，误差 ${w.value}${w.port_pair?`，端口索引对 ${w.port_pair.join('/')}`:''}`:'无有效点'}</Text>
}
function StatisticsView({title,value}:{title:string;value:Statistics|null|undefined}) {
 return <section aria-label={title}><Title order={5}>{title}</Title>{value?<Stack gap="xs"><Text>源帧：{value.frames.join(', ')}；缺失帧：{value.missing_frames.join(', ')||'无'}；实际抽头：{metric(value.actual_taps_min)}–{metric(value.actual_taps_max)}</Text><MetricView label="八路整体矩阵 NMSE（线性）" value={value.matrix_nmse}/><MetricView label="相位误差（度）" value={value.phase_error_deg}/><details><summary>相对同策略未拆簇基线的改善与退化点数</summary><pre>{JSON.stringify(value.changes_against_same_strategy_baseline,null,2)}</pre></details></Stack>:<Text>无结果</Text>}</section>
}
const fields=[['bandwidth_mhz','评估带宽（MHz）',100],['points','评估频点数',41],['amplitude_floor','评估幅度下限',1e-8],['selection_start','选择集起始源帧',0],['selection_end','选择集结束源帧',25],['holdout_start','留出集起始源帧',26],['holdout_end','留出集结束源帧',37],['tap_budget_max','抽头预算上限',31],['matrix_nmse_p95_max','矩阵 NMSE P95 上限',1],['phase_error_p95_max_deg','相位误差 P95 上限（度）',60]] as const
export function MpdbPurposePanel() {
 const [hasAsc,setHasAsc]=useState(false),[manual,setManual]=useState('')
 const holdoutEnd=useRef<HTMLInputElement>(null)
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Purpose|null>(null)
 async function evaluate(event:FormEvent<HTMLFormElement>) {
  event.preventDefault();const body=new FormData(event.currentTarget);setError('');setResult(null)
  try {
   const asc=body.get('asc');const withAsc=asc instanceof File&&asc.size>0
   if(withAsc&&asc.size>256*1024*1024) throw Error('ASC 压缩包不得超过 256 MiB。')
   if(!withAsc) body.delete('asc')
   const n=(key:string)=>Number(body.get(key))
   const p=purposeParameters({selection_start:n('selection_start'),selection_end:n('selection_end'),holdout_start:n('holdout_start'),holdout_end:n('holdout_end'),tap_budget_max:n('tap_budget_max'),matrix_nmse_p95_max:n('matrix_nmse_p95_max'),phase_error_p95_max_deg:n('phase_error_p95_max_deg'),objective:String(body.get('objective')),mode:String(body.get('mode')),manual_candidate:String(body.get('manual_candidate'))},withAsc)
   const grid=comparisonParameters(n('bandwidth_mhz'),n('points'),n('amplitude_floor'))
   for(const [key,limit] of [['archive',256],['members',32]] as const) {const f=body.get(key);if(!(f instanceof File)||!f.size||f.size>limit*1024*1024) throw Error(`${key} 文件不能为空且不得超过 ${limit} MiB。`)}
   for(const [key,v] of Object.entries({...p,...grid})) body.set(key,String(v))
   setBusy(true)
   const {data}=await client.post('/channel-assets/mpdb-projects/purpose-evaluations',body,{timeout:31*60*1000})
   setResult(readPurpose(data))
  } catch(cause) {const detail=isAxiosError(cause)?cause.response?.data?.detail:null;setError(typeof detail==='string'?detail:cause instanceof Error?cause.message:'计算失败，请检查服务。')} finally {setBusy(false)}
 }
 const e=result?.evaluation
 return <Stack data-testid="purpose-panel"><Title order={3}>用途约束与独立留出评估</Title>
 <Text>先冻结来源、连续源帧区间、预算及阈值，再计算六组固定成员候选；上传已有八路 ASC 后加入第七个真实候选。仅选择集参与建议；留出集不参与选参。预算是复杂度代价，增加预算可能局部退化。</Text>
 <form onSubmit={evaluate} onChange={()=>{setResult(null);setError('')}}><fieldset disabled={busy}><legend>冻结评估配置</legend><Stack>
 <label>评估原始 MPDB 外层 ZIP <input required type="file" name="archive" accept=".zip"/></label>
 <label>评估同源固定成员 NPZ <input required type="file" name="members" accept=".npz"/></label>
 <label>可选已有传导八路 H 系数 ASC 压缩包 <input type="file" name="asc" accept=".zip" onChange={event=>{const present=!!event.currentTarget.files?.[0]?.size;setHasAsc(present);if(holdoutEnd.current) holdoutEnd.current.value=present?'36':'37';if(!present&&manual==='existing-asc') setManual('')}}/></label>
 <Text size="sm">无 ASC 默认选择 0–25、留出 26–37；上传 ASC 后默认留出 26–36，六组固定成员与 ASC 使用同一冻结范围。改变文件会重置留出末帧，请核对。</Text>
 {fields.map(([name,label,value])=><label key={name}>{label} <input ref={name==='holdout_end'?holdoutEnd:undefined} required name={name} type="number" defaultValue={value} step={name==='bandwidth_mhz'||name==='amplitude_floor'||name.includes('p95')?'any':'1'}/></label>)}
 <label>排序目标 <select name="objective" defaultValue="phase"><option value="phase">相位误差</option><option value="matrix">整体矩阵误差</option></select></label>
 <label>评估模式 <select name="mode" defaultValue="conducted"><option value="conducted">传导辅助分析</option><option value="ota">OTA 辅助分析</option></select></label>
 <label>人工候选 <select name="manual_candidate" value={manual} onChange={event=>setManual(event.currentTarget.value)}><option value="">不指定</option>{(hasAsc?[...candidates,'existing-asc']:candidates).map(c=><option key={c} value={c}>{c}</option>)}</select></label>
 <Text size="sm">阈值为本次示例约束，不是认证标准。计划区间缺源帧即拒绝，不扫描后补。</Text>
 <Button type="submit" loading={busy}>冻结配置并评估</Button></Stack></fieldset></form>
 {busy&&<Text role="status">正在上传并计算，请稍候。</Text>}{error&&<Alert role="alert" color="red">{error}</Alert>}
 {result&&e&&<Stack aria-live="polite" data-testid="purpose-result">
 <Alert color="yellow" title="离线实样计算">无正式判词；硬件效果、时间与时延零点均未核验。不是模拟结果；不会自动采纳。H 是原始复系数列名，不证明水平极化。</Alert>
 <Text>源帧共 {result.source_frame_count} 帧。建议：{e.selected_candidate??'无候选满足本次约束'}。人工候选：{e.manual_candidate??'未指定'}。</Text>
 <Text>OTA 场参考：{e.ota_status==='unverified'?'缺少场参考，未核验':'传导模式未评估'}。</Text>
 <Title order={4}>选择集 {Object.keys(e.selection).length} 候选（仅本区间排序）</Title><div style={{overflowX:'auto'}}><Table aria-label="选择集候选"><Table.Thead><Table.Tr>{['候选','实际抽头','矩阵 P95','相位 P95（度）','矩阵有效点','相位有效点','本次约束'].map(x=><Table.Th key={x}>{x}</Table.Th>)}</Table.Tr></Table.Thead><Table.Tbody>{Object.entries(e.selection).map(([id,s])=><Table.Tr key={id}><Table.Td>{id}</Table.Td><Table.Td>{metric(s.actual_taps_min)}–{metric(s.actual_taps_max)}</Table.Td><Table.Td>{metric(s.matrix_nmse.p95)}</Table.Td><Table.Td>{metric(s.phase_error_deg.p95)}</Table.Td><Table.Td>{s.matrix_nmse.valid}/{s.matrix_nmse.total}</Table.Td><Table.Td>{s.phase_error_deg.valid}/{s.phase_error_deg.total}</Table.Td><Table.Td>{s.constraints_met?'满足本次约束':'不满足本次约束'}</Table.Td></Table.Tr>)}</Table.Tbody></Table></div>
 <details><summary>查看选择集各候选最差点与局部退化</summary>{Object.entries(e.selection).map(([id,s])=><StatisticsView key={id} title={id} value={s}/>)}</details>
 <StatisticsView title="冻结建议的独立留出" value={e.holdout}/><StatisticsView title="人工候选的独立留出（不覆盖建议）" value={e.manual_holdout}/>
 <StatisticsView title="未配对末帧 37 单列复查" value={e.unmatched_frame_review}/>
 <Text>本次共同源帧：{(result.common_frame_ids as number[]).join(', ')}。选择集：{frameRange(e.plan.selection_frames)}；留出集：{frameRange(e.plan.holdout_frames)}。</Text>
 {Object.hasOwn(e.selection,'existing-asc')&&<><Text>ASC 已加入本次真实候选。ASC 没有同策略未拆簇基线，改善与退化计数不适用；空值不代表没有退化。源帧 37 无 ASC 参考，不参与共同范围排序。</Text><details><summary>共同范围外源帧 37 的六组描述值（不参与选参）</summary><pre>{JSON.stringify(result.excluded_source_frame_review,null,2)}</pre></details></>}
 <Group><Anchor href={result.download_url} download>下载用途评估 ZIP</Anchor><Anchor href={result.points_url} download>下载用途逐点 CSV</Anchor></Group>
 <Text size="sm">完整报告全帧扫描仅作描述，不可据留出排名选参。CSV 保留 partition 与 descriptive_only 标识；最差矩阵点是八路整体误差，端口对索引见来源详情。下载 24 小时后过期，404 请重新评估。</Text>
 <details><summary>冻结计划、来源及选择指纹</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({plan:e.plan,provenance:e.provenance,plan_fingerprint:e.plan_fingerprint,selection_input_fingerprint:e.selection_input_fingerprint,selection_fingerprint:e.selection_fingerprint},null,2)}</pre></details>
 </Stack>}
 </Stack>
}
