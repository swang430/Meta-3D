import { noiseInputError } from './noiseInputError'
import { useRef, useState } from 'react'
import { Alert, FileInput, Stack, Table, Text } from '@mantine/core'
import { previewConductedNoise, buildConductedNoise } from '../../api/roadTestService'

export function ConductedNoisePreview() {
  const turn = useRef(0)
  const [rows,setRows] = useState<Awaited<ReturnType<typeof previewConductedNoise>>['windows']>([])
  const [error,setError] = useState('')
  const [wave,setWave] = useState<Blob | null>(null)
  async function read(file: File | null) {
    const request = ++turn.current
    setRows([]); setError(''); setWave(null)
    if (!file) return
    try {
      if (file.size > 16*1024*1024) throw Error('输入文件超过 16 MiB')
      const input = JSON.parse(await file.text())
      const result = await previewConductedNoise(Array.isArray(input) ? input : input.windows)
      if (turn.current !== request) return
      setRows(result.windows)
      if (!Array.isArray(input)) {
        const output = await buildConductedNoise(input)
        if (turn.current === request) setWave(new Blob([JSON.stringify(output)],{type:'application/json'}))
      }
    } catch (e) {
      if (turn.current !== request) return
      setError(noiseInputError(e))
    }
  }
  return <details><summary>按系统仿真预览干扰和噪声</summary><Stack gap="xs">
    <FileInput label="系统仿真统计窗口或带多端口波形的 JSON" accept=".json" clearable onChange={read}/>
    {error && <Alert color="red">{error}</Alert>}
    {rows.length>0 && <><Text>以下为离线预测，未向仪器注入信号。</Text><Table><Table.Thead><Table.Tr>
      {['帧','接收口','所需干扰加噪声总量（dBm）','新增功率（dBm）','依据'].map(x=><Table.Th key={x}>{x}</Table.Th>)}
    </Table.Tr></Table.Thead><Table.Tbody>{rows.map((r,i)=><Table.Tr key={i}><Table.Td>{r.scope.frame}</Table.Td><Table.Td>{r.scope.receiver}</Table.Td><Table.Td>{r.total_disturbance_dbm?.toFixed(2)??'未核验'}</Table.Td><Table.Td>{r.additional_dbm?.toFixed(2)??'—'}</Table.Td><Table.Td>{r.reason || '按同一插口和统计窗口计算'}</Table.Td></Table.Tr>)}</Table.Tbody></Table></>}
    {wave && <button type="button" onClick={()=>{const url=URL.createObjectURL(wave);const a=document.createElement('a');a.href=url;a.download='conducted-noise-samples.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}}>下载离线复基带样本</button>}
  </Stack></details>
}
