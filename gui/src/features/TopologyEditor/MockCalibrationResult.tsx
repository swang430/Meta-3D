import {useState} from 'react'
import {Alert,Button,Card,Stack,Text} from '@mantine/core'
import type {FixedRouteRecord} from '../../types/api'
import {fixedRouteDisplay} from '../LabWorkspace/fixedRouteDisplay'
import {exportMockCalibrationCsv} from './mockCalibrationCsv'

/** 仅消费服务器记录；不从表单草稿拼出结果或时间。 */
export function MockCalibrationResult({records}:{records:FixedRouteRecord[]}) {
 const [error,setError]=useState('')
 const rows=records.filter(r=>fixedRouteDisplay(r).mock)
 if(!rows.length)return null
 const db=(n:number|null|undefined)=>n==null?'未计算':`${n.toFixed(4)} dB`
 return <Card withBorder data-testid="mock-calibration-result"><Stack gap="xs">
  <Text fw={600}>模拟演练（非实测）· 不可正式采用／不是正式报告</Text>
  {rows.map(r=>{const result=r.result!,mock=fixedRouteDisplay(r).mock!;return <Stack gap={2} key={`${r.lab_profile_id}:${r.run_id}`}>
   <Text size="xs">run：{r.run_id} · Lab：{r.lab_profile_id} · {result.request.chain_id} · {result.request.frequency_mhz} MHz</Text>
   <Text>服务器净损耗：{db(mock.netLoss)}；样本标准差：{db(mock.std)}</Text>
   <Text>expected：{db(mock.expected)}；差值（服务器net − expected）：{db(mock.expectedDelta)}；不产生PASS判词。</Text>
   <Text size="xs">来源：{result.simulation_input_source??'未知（禁止导出）'}；formal_eligible=false；时间性质：演练处理时间（非硬件时间）</Text>
   {mock.netLoss===null&&<Text size="sm">只留样本，不计算损耗；请核对接收线损及来源。</Text>}
   {(result.samples??[]).map((s,i)=><Text size="xs" key={i}>样本{i+1}：前{s.source_before_dbm} / 接收{s.received_dbm} / 后{s.source_after_dbm} dBm · 演练处理时间 {s.host_time}</Text>)}
  </Stack>})}
  <Button variant="light" onClick={()=>{try{
   const text=exportMockCalibrationCsv(rows),url=URL.createObjectURL(new Blob(['\uFEFF'+text],{type:'text/csv;charset=utf-8'}))
   const link=document.createElement('a');link.href=url;link.download=`mock-calibration-${String(rows[0].result?.states?.batch_job_id??rows[0].run_id)}.csv`
   document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);setError('')
  }catch(e){setError(e instanceof Error?e.message:'导出失败')}}}>下载模拟演练 CSV（非正式报告）</Button>
  {error&&<Alert color="red">{error}</Alert>}
 </Stack></Card>
}
