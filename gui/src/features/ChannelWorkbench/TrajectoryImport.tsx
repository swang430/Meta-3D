import { useState } from 'react'
import { Alert, Button, Checkbox, FileInput, Group, NumberInput, Select, Stack } from '@mantine/core'

export function downloadFile(name: string, file: Blob) {
  const url = URL.createObjectURL(file)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function TrajectoryImport({ onImport }: { onImport: (file: File) => void }) {
  const [direction, setDirection] = useState('downlink')
  const [speed, setSpeed] = useState<string | number>('')
  const [metres, setMetres] = useState(false)
  const [files, setFiles] = useState<Record<string, File | null>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function convert() {
    setError('')
    setBusy(true)
    try {
      const body = new FormData()
      for (const [key, file] of Object.entries(files)) if (file) body.set(key, file)
      body.set('direction', direction)
      body.set('speed_m_s', String(speed))
      body.set('coordinate_units', 'metres')
      const res = await fetch('/api/v1/channel-assets/trajectory/import', { method: 'POST', body })
      const data = await res.json()
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '导入失败，请核对文件与速度')
      onImport(new File([JSON.stringify(data)], direction + '.json', { type: 'application/json' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '导入失败')
    } finally {
      setBusy(false)
    }
  }
  return <fieldset disabled={busy}><legend>从原始文件导入轨迹</legend><Stack>
    <Select label="计算方向" value={direction} allowDeselect={false} onChange={value => value && setDirection(value)}
      data={[{ value: 'downlink', label: '下行' }, { value: 'uplink', label: '上行' }]} />
    {Object.entries({ archive: '包含上下行 MPDB 的原始 ZIP 包', clusters: '该方向的聚簇 CSV', quality: '该方向的质量 CSV', manifest: '新批次的配套清单 JSON（已评估的原交付可省略）' }).map(([key, label]) =>
      <FileInput key={key} label={label} value={files[key] ?? null} onChange={file => setFiles(old => ({ ...old, [key]: file }))} />)}
    <Group><NumberInput label="轨迹恒速（米/秒）" value={speed} onChange={setSpeed} />
      <Checkbox label="按米解释轨迹坐标，以距离和恒速推算时刻" checked={metres} onChange={e => setMetres(e.currentTarget.checked)} /></Group>
    <Button loading={busy} disabled={!metres || !(Number(speed) > 0) || !files.archive || !files.clusters || !files.quality} onClick={convert}>生成交换文件</Button>
    {error && <Alert color="red">{error}</Alert>}
  </Stack></fieldset>
}
