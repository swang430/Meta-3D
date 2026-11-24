import { useState, type FormEvent } from 'react'
import { Alert, Anchor, Button, Group, ScrollArea, Stack, Table, Text, Title } from '@mantine/core'
import { isAxiosError } from 'axios'
import client from '../../api/client'
import { comparisonParameters, metric } from './comparison'
import { readBudget, type Budget } from './budget'

export function MpdbBudgetPanel() {
 const [busy,setBusy]=useState(false)
 const [error,setError]=useState('')
 const [result,setResult]=useState<Budget|null>(null)
 async function compare(event:FormEvent<HTMLFormElement>) {
  event.preventDefault()
  const body=new FormData(event.currentTarget)
  setResult(null);setError('')
  try {
   const parameters=comparisonParameters(Number(body.get('bandwidth_mhz')),Number(body.get('points')),Number(body.get('amplitude_floor')))
   for(const [name,limit] of [['archive',256],['members',32]] as const) {
    const file=body.get(name)
    if(!(file instanceof File)||!file.size||file.size>limit*1024*1024) throw Error(`${name==='archive'?'原始 MPDB ZIP':'同源成员表'}不能为空且不得超过 ${limit} MiB。`)
   }
   for(const [key,value] of Object.entries(parameters)) body.set(key,String(value))
   setBusy(true)
   const {data}=await client.post('/channel-assets/mpdb-projects/budget-comparisons',body,{timeout:31*60*1000})
   setResult(readBudget(data))
  } catch(cause) {
   const detail=isAxiosError(cause)?cause.response?.data?.detail:null
   setError(typeof detail==='string'?detail:cause instanceof Error?cause.message:'计算未完成，请检查服务连接。')
  } finally {setBusy(false)}
 }
 return <Stack data-testid="budget-panel">
  <Title order={3}>抽头预算比较</Title>
  <Text>使用原始 MPDB 与同源固定成员，比较端口独立功率加权时延、八路共享功率加权时延，预算为 24、26、31。不重新聚簇，不写回或自动采纳工程。</Text>
  <form onSubmit={compare} onChange={()=>{setResult(null);setError('')}}><fieldset disabled={busy}><legend>预算比较文件与参数</legend><Stack>
   <label>原始 MPDB 外层 ZIP（最大 256 MiB） <input required type="file" name="archive" accept=".zip" /></label>
   <label>同源射线成员表（members.npz，最大 32 MiB） <input required type="file" name="members" accept=".npz" /></label>
   <Text size="sm">成员标签须对应源行筛选非零 H 后的固定成员。H 是复系数列名，不证明水平极化。</Text>
   <label>比较带宽（MHz） <input required type="number" name="bandwidth_mhz" defaultValue="100" max="10000" step="any" /></label>
   <label>频点数（3 至 257 的奇数） <input required type="number" name="points" defaultValue="41" min="3" max="257" step="2" /></label>
   <label>共同相位掩码的幅度下限 <input required type="number" name="amplitude_floor" defaultValue="1e-8" step="any" /></label>
   <Button type="submit" loading={busy}>开始预算比较</Button>
  </Stack></fieldset></form>
  {busy&&<Text role="status">正在上传并计算全部源帧，请稍候。</Text>}
  {error&&<Alert color="red" role="alert">{error}</Alert>}
  {result&&<Stack aria-live="polite">
   <Alert color="yellow" title="证据未核验">仅离线辅助分析；无正式通过结论，时间与零点对齐未核验。非模拟结果，硬件效果未核验。</Alert>
   <Text>源帧共 {result.source_frame_count} 帧，全部参与源帧比较（含末帧 {result.frame_ids.at(-1)}）。</Text>
   <Text>预算是上限；实际使用范围跨全部帧与端口，稀疏端口不补齐。增预算仍可能局部变差。</Text>
   <ScrollArea><Table withTableBorder aria-label="抽头预算结果"><Table.Thead><Table.Tr>{['策略','预算上限','实际使用范围','矩阵 NMSE 中位数（线性）','矩阵 NMSE P95（线性）','相位误差 P95（度）','共同有效相位点','改善点','变差点','不变点'].map(x=><Table.Th key={x}>{x}</Table.Th>)}</Table.Tr></Table.Thead><Table.Tbody>
    {['independent','shared'].flatMap(strategy=>[24,26,31].map(budget=>{const r=result.summary[`${strategy}-${budget}`];return <Table.Tr key={`${strategy}-${budget}`} data-testid={`${strategy}-${budget}`}><Table.Td>{strategy==='independent'?'端口独立功率加权时延':'八路共享功率加权时延'}</Table.Td><Table.Td>{budget}</Table.Td><Table.Td>{r.used_taps_min===r.used_taps_max?r.used_taps_min:`${r.used_taps_min}–${r.used_taps_max}`}</Table.Td>{[r.matrix_nmse_median,r.matrix_nmse_p95,r.phase_error_p95_deg].map((v,i)=><Table.Td key={i}>{metric(v)}</Table.Td>)}{[r.common_valid,r.improved,r.worse,r.unchanged].map((v,i)=><Table.Td key={i}>{v}</Table.Td>)}</Table.Tr>}))}
   </Table.Tbody></Table></ScrollArea>
   <Text size="sm">改善、变差、不变仅比较同策略与自身 24 抽头基线的共同有效相位点，容差 1e-7 度。矩阵变化请查看 CSV 的 matrix_delta；无有效数值显示“无有效点”。</Text>
   <Group><Anchor href={result.download_url} download>下载预算完整报告 ZIP</Anchor><Anchor href={result.points_url} download>下载预算逐点 CSV</Anchor></Group>
   <Text>定位方法：CSV 按 frame、strategy、tap_budget、offset_hz、port_a/b 筛选；端口索引见来源详情。phase_delta_deg 与 matrix_delta 均为当前减同策略 24 抽头值，负数表示改善。ZIP 内 report.json 提供逐帧八路实际抽头数、簇排序与分界。下载 24 小时后过期，404 时请重新比较。</Text>
   <details><summary>查看预算比较来源与定位索引</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({source:result.source,mpdb_sha256:result.mpdb_sha256,frame_ids:result.frame_ids,port_order:result.port_order,port_pairs:result.port_pairs,offsets_hz:result.offsets_hz,amplitude_floor:result.amplitude_floor},null,2)}</pre></details>
  </Stack>}
 </Stack>
}
