import { TrajectoryImport, downloadJson } from './TrajectoryImport'
import { useState } from 'react'
import { Alert, Button, FileInput, Paper, ScrollArea, Stack, Table, Text } from '@mantine/core'

interface Frame {
  sampleIndex: number
  frameId: number | null
  timeSeconds: number
  reason: string | null
  real: number[] | null
  imag: number[] | null
}
interface Result {
  direction: 'downlink' | 'uplink'
  offsetsHz: number[]
  frames: Frame[]
}

export function ClusterResponsePanel() {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  async function calculate() {
    if (!file) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const trajectory = JSON.parse(await file.text())
      if (!['uplink', 'downlink'].includes(trajectory.direction)) throw new Error('轨迹文件缺少上下行方向')
      const response = await fetch('/api/v1/ota/cluster-response', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trajectory, direction: trajectory.direction, offsets_hz: [-5000000, -2500000, 0, 2500000, 5000000] }),
      })
      if (!response.ok) {
        const message = await response.json()
        throw new Error(typeof message.detail === 'string' ? message.detail : '计算服务未能处理该轨迹')
      }
      setResult(await response.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取轨迹或计算失败')
    } finally {
      setBusy(false)
    }
  }
  return <Paper withBorder p="md"><Stack>
    <TrajectoryImport onImport={value => { setFile(value); setResult(null); setError('') }} />
    <FileInput label="聚簇轨迹文件" accept=".json" disabled={busy} value={file}
      onChange={value => { setFile(value); setResult(null); setError('') }} />
    {file && <Button variant="light" onClick={async () => downloadJson(file.name, JSON.parse(await file.text()))}>下载交换文件</Button>}
    <Button disabled={!file} loading={busy} onClick={calculate}>计算逐帧模型频响</Button>
    {error && <Alert color="red">{error}</Alert>}
    {result && <>
      <Button onClick={() => downloadJson(result.direction + '-response.json', result)}>下载逐帧计算结果</Button>
      <Text>{result.direction === 'uplink' ? '上行' : '下行'}共 {result.frames.length} 帧。数值为模型计算结果，设备播放尚未验证。</Text>
      <ScrollArea.Autosize mah={350}><Table><Table.Thead><Table.Tr>
        <Table.Th>帧编号</Table.Th><Table.Th>时刻（秒）</Table.Th>
        {result.offsetsHz.map(hz => <Table.Th key={hz}>{hz / 1e6} MHz 偏移（实部，虚部）</Table.Th>)}
      </Table.Tr></Table.Thead><Table.Tbody>{result.frames.map(frame => <Table.Tr key={frame.sampleIndex}>
        <Table.Td>{frame.frameId ?? '未知'}</Table.Td><Table.Td>{frame.timeSeconds}</Table.Td>
        {result.offsetsHz.map((hz, i) => <Table.Td key={hz}>{frame.real && frame.imag
          ? [frame.real[i], frame.imag[i]].map(x => x.toPrecision(6)).join('，')
          : frame.reason ?? '缺测'}</Table.Td>)}
      </Table.Tr>)}</Table.Tbody></Table></ScrollArea.Autosize>
    </>}
  </Stack></Paper>
}
