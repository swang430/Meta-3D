import type { BatchMockInput, BatchPlanRequest, FixedRouteRecord } from '../../types/api'
import { fixedRouteDisplay } from '../LabWorkspace/fixedRouteDisplay.ts'

export type MockCsvImport={mockInputs:BatchMockInput[];references:BatchPlanRequest['references']}
const columns=['chain_id','frequency_mhz','sample_index','source_before_dbm','received_dbm','source_after_dbm','receive_cable_loss_db','receive_cable_source','expected_loss_db']
const key=(chain:string,frequency:number)=>JSON.stringify([chain,frequency])
const finite=(raw:string,label:string)=>{if(!raw.trim())throw new Error(`${label}不能为空`);const n=Number(raw);if(!Number.isFinite(n))throw new Error(`${label}须为有限数值`);return n}
const optional=(raw:string,label:string)=>raw.trim()?finite(raw,label):null

/** RFC4180 字符扫描，不把引号内逗号或换行拆成列。 */
function rows(text:string):{cells:string[];line:number}[] {
 const result:{cells:string[];line:number}[]=[],cells:string[]=[]
 let field='',quoted=false,closed=false,line=1,start=1
 const cell=()=>{cells.push(field);field='';closed=false}
 const row=()=>{cell();if(cells.some(c=>c.trim()))result.push({cells:[...cells],line:start});cells.length=0}
 text=text.replace(/^\uFEFF/,'')
 for(let i=0;i<text.length;i++){
  const c=text[i]
  if(quoted){if(c==='"'){if(text[i+1]==='"'){field+='"';i++}else{quoted=false;closed=true}}else{field+=c;if(c==='\n')line++}continue}
  if(c==='"'){if(field||closed)throw new Error(`行${line}：引号位置无效`);quoted=true}
  else if(c===',')cell()
  else if(c==='\r'||c==='\n'){row();if(c==='\r'&&text[i+1]==='\n')i++;line++;start=line}
  else{if(closed)throw new Error(`行${line}：闭合引号后有额外字符`);field+=c}
 }
 if(quoted)throw new Error(`行${start}：引号未闭合`)
 row();return result
}

export function parseMockCalibrationCsv(text:string,selection:{chainIds:string[];frequenciesMhz:number[];sampleCount:number;referenceAntennas:Record<string,string>}):MockCsvImport {
 const parsed=rows(text),header=parsed.shift()?.cells
 if(!header||header.length!==columns.length||new Set(header).size!==header.length||header.some(c=>!columns.includes(c)))throw new Error('行1：CSV列须完整、唯一且无未知字段')
 if(!selection.chainIds.length||new Set(selection.chainIds).size!==selection.chainIds.length||!selection.frequenciesMhz.length||new Set(selection.frequenciesMhz).size!==selection.frequenciesMhz.length||selection.frequenciesMhz.some(f=>!Number.isFinite(f)||f<=0)||!Number.isInteger(selection.sampleCount)||selection.sampleCount<2||selection.sampleCount>10)throw new Error('请先选择路径、有效频点及2–10个样本')
 const groups=new Map<string,{input:BatchMockInput;reference:BatchPlanRequest['references'][number];samples:Map<number,BatchMockInput['samples'][number]>}>()
 for(const chain of selection.chainIds)for(const frequency of selection.frequenciesMhz){
  const antenna=selection.referenceAntennas[chain]?.trim();if(!antenna)throw new Error(`${chain}：先填写已核对参考天线及位置`)
  groups.set(key(chain,frequency),{input:{chain_id:chain,frequency_mhz:frequency,samples:[],expected_loss_db:null},reference:{chain_id:chain,frequency_mhz:frequency,reference_antenna:antenna,receive_cable_loss_db:null,receive_cable_source:null},samples:new Map()})
 }
 for(const row of parsed){
  const label=`行${row.line}`
  if(row.cells.length!==header.length)throw new Error(`${label}：列数不符`)
  const v=Object.fromEntries(header.map((c,i)=>[c,row.cells[i]])),chain=v.chain_id.trim(),frequency=finite(v.frequency_mhz,`${label} frequency_mhz`),group=groups.get(key(chain,frequency))
  if(frequency<=0||!group)throw new Error(`${label}：非所选组 ${chain} @${frequency}`)
  const context=`${label} ${chain} @${frequency}`
  if(!/^[1-9]\d*$/.test(v.sample_index.trim()))throw new Error(`${context} sample_index须为十进制整数`)
  const index=Number(v.sample_index)
  if(index>selection.sampleCount||group.samples.has(index))throw new Error(`${context} sample_index超范围或重复`)
  const cable=optional(v.receive_cable_loss_db,`${context} receive_cable_loss_db`),source=v.receive_cable_source.trim()||null,expected=optional(v.expected_loss_db,`${context} expected_loss_db`)
  if(group.samples.size&&(cable!==group.reference.receive_cable_loss_db||source!==group.reference.receive_cable_source||expected!==group.input.expected_loss_db))throw new Error(`${context}：receive_cable_loss_db / receive_cable_source / expected_loss_db 同组公共值冲突`)
  group.reference.receive_cable_loss_db=cable;group.reference.receive_cable_source=source;group.input.expected_loss_db=expected
  group.samples.set(index,{source_before_dbm:finite(v.source_before_dbm,`${context} source_before_dbm`),received_dbm:finite(v.received_dbm,`${context} received_dbm`),source_after_dbm:finite(v.source_after_dbm,`${context} source_after_dbm`)})
 }
 for(const group of groups.values()){
  if(group.samples.size!==selection.sampleCount)throw new Error(`${group.input.chain_id} @${group.input.frequency_mhz}：缺少样本，须完整1..${selection.sampleCount}`)
  group.input.samples=Array.from({length:selection.sampleCount},(_,i)=>group.samples.get(i+1)!)
 }
 return {mockInputs:[...groups.values()].map(g=>g.input),references:[...groups.values()].map(g=>g.reference)}
}

export function exportMockCalibrationCsv(records:FixedRouteRecord[]):string {
 if(!records.length)throw new Error('无服务器演练记录')
 const output:string[][]=[['run_id','lab_profile_id',...columns,'net_loss_db','sample_std_db','expected_delta_db','simulation_input_source','formal_eligible','host_time','time_basis']]
 const encode=(v:unknown,text=false)=>{let s=v==null?'':String(v);if(text&&/^\s*[=+\-@]/.test(s))s="'"+s;return /[,"\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s}
 for(const record of records){
  const result=record.result,mock=fixedRouteDisplay(record).mock
  if(!record.run_id||!record.lab_profile_id||!result||result.run_id!==record.run_id||result.lab_profile_id!==record.lab_profile_id||!mock||result.simulation_input_source!=='operator_supplied_synthetic'||!result.samples?.length)throw new Error('仅能导出身份一致且具服务器来源及样本的演练结果')
  result.samples.forEach((s,i)=>output.push([encode(record.run_id,true),encode(record.lab_profile_id,true),encode(result.request.chain_id,true),encode(result.request.frequency_mhz),encode(i+1),encode(s.source_before_dbm),encode(s.received_dbm),encode(s.source_after_dbm),encode(result.request.receive_cable_loss_db),encode(result.request.receive_cable_source,true),encode(mock.expected),encode(mock.netLoss),encode(mock.std),encode(mock.expectedDelta),encode(result.simulation_input_source,true),'false',encode(s.host_time,true),'simulation_processing_time']))
 }
 return output.map(row=>row.join(',')).join('\r\n')
}
